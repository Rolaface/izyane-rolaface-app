from custom_api.utils.response import send_response
from frappe.utils import nowdate, date_diff, getdate
import frappe


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_supplier_statement():
    supplier_id = frappe.form_dict.get("supplierId")
    page = int(frappe.form_dict.get("page", 1))
    page_size = int(frappe.form_dict.get("page_size", 10))
    start = (page - 1) * page_size

    if not supplier_id:
        return send_response(
            status="fail",
            message="Supplier id must not be null",
            data={},
            status_code=400,
            http_status=400
        )

    supplier = frappe.db.get_value("Supplier", supplier_id, ["name", "creation"], as_dict=True)

    if not supplier:
        return send_response(
            status="fail",
            message=f"Supplier with id {supplier_id} not found.",
            data={},
            status_code=404,
            http_status=404
        )

    opening_balance = 0
    opening_date = getdate(supplier.creation) if supplier.creation else None

    summary = frappe.db.sql("""
        SELECT 
            COUNT(pi.name) AS total_billed,
            COALESCE(SUM(pi.grand_total), 0) AS total_billed_amount
        FROM `tabPurchase Invoice` pi
        WHERE pi.supplier=%s AND pi.docstatus=1
    """, (supplier_id,), as_dict=True)[0]

    total_paid = frappe.db.sql("""
        SELECT COALESCE(SUM(ref.allocated_amount), 0)
        FROM `tabPayment Entry Reference` ref
        JOIN `tabPayment Entry` pe ON pe.name = ref.parent
        WHERE pe.docstatus=1
          AND ref.reference_doctype='Purchase Invoice'
          AND ref.reference_name IN (
              SELECT name FROM `tabPurchase Invoice`
              WHERE supplier=%s AND docstatus=1
          )
    """, (supplier_id,))[0][0] or 0

    total_billed = summary.get("total_billed") or 0
    total_billed_amount = summary.get("total_billed_amount") or 0

    net_outstanding = total_billed_amount - total_paid + opening_balance

    aging = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "90_plus": 0}

    invoices = frappe.db.sql("""
        SELECT due_date, outstanding_amount
        FROM `tabPurchase Invoice`
        WHERE supplier=%s AND docstatus=1 AND outstanding_amount > 0
    """, (supplier_id,), as_dict=True)

    today = nowdate()

    for inv in invoices:
        due_date = inv.get("due_date") or today
        outstanding = inv.get("outstanding_amount") or 0
        days_overdue = date_diff(today, due_date)

        if days_overdue <= 0:
            aging["current"] += outstanding
        elif days_overdue <= 30:
            aging["1_30"] += outstanding
        elif days_overdue <= 60:
            aging["31_60"] += outstanding
        elif days_overdue <= 90:
            aging["61_90"] += outstanding
        else:
            aging["90_plus"] += outstanding

    total_ledger_entries = frappe.db.count("GL Entry", {
        "party_type": "Supplier",
        "party": supplier_id,
        "is_cancelled": 0
    })

    running_balance = opening_balance

    if start > 0:
        prev_balance = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(debit_in_account_currency - credit_in_account_currency), 0)
            FROM `tabGL Entry`
            WHERE party_type='Supplier'
              AND party=%s
              AND is_cancelled=0
            ORDER BY posting_date ASC, creation ASC
            LIMIT %s
        """, (supplier_id, start))[0][0] or 0

        running_balance += prev_balance

    gl_rows = frappe.db.sql("""
        SELECT 
            posting_date,
            voucher_type,
            voucher_no,
            debit_in_account_currency AS debit,
            credit_in_account_currency AS credit
        FROM `tabGL Entry`
        WHERE party_type='Supplier'
          AND party=%s
          AND is_cancelled=0
        ORDER BY posting_date ASC, creation ASC
        LIMIT %s OFFSET %s
    """, (supplier_id, page_size, start), as_dict=True)

    voucher_map = {
        "Purchase Invoice": [],
        "Payment Entry": [],
        "Journal Entry": []
    }

    for row in gl_rows:
        vt = row.get("voucher_type")
        if vt in voucher_map:
            voucher_map[vt].append(row.get("voucher_no"))

    remarks_map = {}

    if voucher_map["Purchase Invoice"]:
        rows = frappe.db.get_all("Purchase Invoice",
            filters={"name": ["in", voucher_map["Purchase Invoice"]]},
            fields=["name", "remarks"]
        )
        remarks_map.update({r.name: r.remarks for r in rows})

    if voucher_map["Payment Entry"]:
        rows = frappe.db.get_all("Payment Entry",
            filters={"name": ["in", voucher_map["Payment Entry"]]},
            fields=["name", "remarks"]
        )
        remarks_map.update({r.name: r.remarks for r in rows})

    if voucher_map["Journal Entry"]:
        rows = frappe.db.get_all("Journal Entry",
            filters={"name": ["in", voucher_map["Journal Entry"]]},
            fields=["name", "user_remark"]
        )
        remarks_map.update({r.name: r.user_remark for r in rows})

    ledger = []

    if page == 1:
        ledger.append({
            "date": opening_date,
            "type": "Opening Balance",
            "ref": "BAL-FWD",
            "debit": 0,
            "credit": 0,
            "balance": running_balance,
            "note": ""
        })

    for row in gl_rows:
        debit = row.get("debit") or 0
        credit = row.get("credit") or 0

        running_balance += debit - credit

        ledger.append({
            "date": row.get("posting_date"),
            "type": row.get("voucher_type"),
            "ref": row.get("voucher_no"),
            "debit": debit,
            "credit": credit,
            "balance": running_balance,
            "note": remarks_map.get(row.get("voucher_no"), "") or ""
        })

    total_pages = (total_ledger_entries + page_size - 1) // page_size

    statement = {
        "openingBalance": opening_balance,
        "summary": {
            "totalBilled": total_billed,
            "totalPaid": total_paid,
            "netOutstanding": net_outstanding
        },
        "aging": aging,
        "ledger": ledger,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total_ledger_entries,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }

    return send_response(
        status="success",
        message="Supplier statement retrieved successfully",
        data=statement,
        status_code=200,
        http_status=200
    )