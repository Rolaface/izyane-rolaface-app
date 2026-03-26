from erpnext.zra_client.generic_api import send_response_list
import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from custom_api.utils.response import send_response
from frappe.desk.search import search_widget
from erpnext.zra_client.generic_api import send_response as old_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_ledger_account():
    try:
        payment_type = frappe.request.args.get("paymentType", "Pay")
        filter       = frappe.request.args.get("filter", "to")
        txt          = frappe.request.args.get("search", "")
        party_type   = frappe.request.args.get("partyType", "Customer")

        company = frappe.defaults.get_user_default("Company")

        # ── Account type maps per party_type ──────────────────────────────────
        account_type_map = {
            "Customer": {
                "from": ["Bank", "Cash"],
                "to":   ["Receivable"],
            },
            "Supplier": {
                "from": ["Bank", "Cash"],
                "to":   ["Payable"],
            },
            "Employee": {
                "from": ["Bank", "Cash"],
                "to":   ["Payable"],
            },
            "Shareholder": {
                "from": ["Bank", "Cash", "Equity"],
                "to":   ["Payable", "Equity"],
            },
        }

        # Fallback to Customer if party_type not found
        party_map = account_type_map.get(party_type, account_type_map["Customer"])

        # ── Determine filter direction based on payment_type ──────────────────
        # Pay:     money goes OUT → "from" = Bank/Cash, "to" = Payable/Receivable
        # Receive: money comes IN → "from" = Payable/Receivable, "to" = Bank/Cash
        if payment_type == "Receive":
            resolved_filter = "to" if filter == "from" else "from"
        else:
            resolved_filter = filter

        account_types = party_map.get(resolved_filter, ["Bank", "Cash"])

        filters = {
            "account_type": ["in", account_types],
            "is_group": 0,
            "company": company
        }

        response = search_widget(
            "Account",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            filter_fields='["account_currency"]',
            reference_doctype="Payment Entry",
            ignore_user_permissions=0,
            as_dict=True,
        )

        return old_response(
            status="success",
            message="Ledger accounts fetched successfully.",
            data=response,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Ledger Account API Error")
        return old_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )

def validate_required(data, fields):
    for field in fields:
        if not data.get(field):
            return field
    return None


def resolve_party_name(party_type, party_id):
    doctype_map = {
        "Customer":    ("Customer",    "custom_id"),
        "Supplier":    ("Supplier",    "custom_id"),
        "Employee":    ("Employee",    "name"),
        "Shareholder": ("Shareholder", "custom_id"),
    }
    doctype, id_field = doctype_map.get(party_type, (None, None))
    if not doctype:
        return None
    return frappe.db.get_value(doctype, {id_field: party_id}, "name")


def build_references(references, pe):
    for ref in references:
        reference_doctype = ref.get("reference_doctype")
        reference_name    = ref.get("reference_name")
        allocated_amount  = float(ref.get("allocated_amount") or 0)

        if not reference_doctype or not reference_name:
            continue

        outstanding = frappe.db.get_value(
            reference_doctype, reference_name, "outstanding_amount"
        ) or 0

        total_amount = frappe.db.get_value(
            reference_doctype, reference_name, "grand_total"
        ) or 0

        pe.append("references", {
            "reference_doctype":  reference_doctype,
            "reference_name":     reference_name,
            "due_date":           ref.get("due_date"),
            "total_amount":       total_amount,
            "outstanding_amount": outstanding,
            "allocated_amount":   allocated_amount,
        })


def build_taxes(taxes, pe):
    for tax in taxes:
        pe.append("taxes", {
            "charge_type":    tax.get("type", "Actual"),
            "account_head":   tax.get("account_head"),
            "rate":           float(tax.get("tax_rate") or 0),
            "tax_amount":     float(tax.get("amount") or 0),
            "total":          float(tax.get("total") or 0),
            "description":    tax.get("account_head"),
        })


@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_payment_entry():
    try:
        data = frappe.request.get_json()

        if not data:
            return send_response(
                status="error",
                message="Request body is required.",
                data=None,
                status_code=400,
                http_status=400
            )

        # ── Required fields ───────────────────────────────────────────────────
        required = [
            "payment_type", "party_type", "party_id",
            "mode_of_payment", "payment_date",
            "paid_from", "paid_to",
            "paid_from_amount"
        ]
        missing = validate_required(data, required)
        if missing:
            return old_response(
                status="error",
                message=f"'{missing}' is required.",
                data=None,
                status_code=400,
                http_status=400
            )
        
        company = frappe.defaults.get_user_default("Company")
        company_currency = frappe.db.get_value("Company", company, "default_currency")

        # ── Extract fields ────────────────────────────────────────────────────
        payment_type     = data.get("payment_type")
        party_type       = data.get("party_type")
        party_id         = data.get("party_id")
        payment_mode     = data.get("mode_of_payment")
        payment_date     = data.get("payment_date")
        reference_no     = data.get("reference_no", "")
        reference_date   = data.get("reference_date") or payment_date
        project          = data.get("project")
        cost_center      = data.get("cost_center")
        exchange_rate    = float(data.get("exchange_rate") or 1)

        paid_from                 = data.get("paid_from")
        paid_from_bank_account    = data.get("paid_from_bank_account", "")
        paid_from_currency        = data.get("paid_from_account_currency", company_currency)
        paid_amount               = float(data.get("paid_from_amount") or 0)

        paid_to                   = data.get("paid_to")
        paid_to_bank_account      = data.get("paid_to_bank_account", "")
        paid_to_currency          = data.get("paid_to_account_currency", company_currency)
        received_amount           = float(data.get("paid_to_amount") or paid_amount)

        references = data.get("references", [])
        taxes      = data.get("taxes", [])

        company = frappe.defaults.get_user_default("Company")

        # ── Validate payment type ─────────────────────────────────────────────
        valid_payment_types = ["Pay", "Receive", "Internal Transfer"]
        if payment_type not in valid_payment_types:
            return old_response(
                status="error",
                message=f"'paymentType' must be one of: {', '.join(valid_payment_types)}.",
                data=None,
                status_code=400,
                http_status=400
            )

        # ── Validate party type ───────────────────────────────────────────────
        valid_party_types = ["Customer", "Supplier", "Employee", "Shareholder"]
        if party_type not in valid_party_types:
            return old_response(
                status="error",
                message=f"'partyType' must be one of: {', '.join(valid_party_types)}.",
                data=None,
                status_code=400,
                http_status=400
            )

        # ── Resolve party ─────────────────────────────────────────────────────
        party_name = data.get("party_id") or resolve_party_name(party_type, party_id)
        if not party_name:
            return old_response(
                status="error",
                message=f"{party_type} with ID '{party_id}' not found.",
                data=None,
                status_code=404,
                http_status=404
            )
        
        if not (paid_from_currency == paid_to_currency or paid_from_currency == company_currency
                    or paid_to_currency == company_currency
                ):
                return old_response(
                    status="error",
                    message=(
                        "Invalid currency combination: 'paid from account currency' "
                        "and 'paid to account currency' must either be the same "
                        f"or one of them must be the company default currency ({company_currency})."
                    ),
                    data={
                        "paid_from_currency": paid_from_currency,
                        "paid_to_currency": paid_to_currency,
                        "company_currency": company_currency
                    },
                    status_code=400,
                    http_status=400
                )

        # ── Create Payment Entry ──────────────────────────────────────────────
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type               = payment_type
        pe.posting_date               = payment_date
        pe.company                    = company
        pe.mode_of_payment            = payment_mode
        pe.party_type                 = party_type
        pe.party                      = party_name
        pe.paid_from                  = paid_from
        pe.paid_to                    = paid_to
        pe.paid_from_account_currency = paid_from_currency
        pe.paid_to_account_currency   = paid_to_currency
        pe.paid_amount                = paid_amount
        pe.received_amount            = received_amount
        pe.source_exchange_rate       = exchange_rate
        pe.target_exchange_rate       = exchange_rate
        pe.reference_no               = reference_no
        pe.reference_date             = reference_date

        if paid_from_bank_account:
            pe.bank_account = paid_from_bank_account

        if paid_to_bank_account:
            pe.party_bank_account = paid_to_bank_account

        if project:
            pe.project = project

        if cost_center:
            pe.cost_center = cost_center

        # ── Invoices tab — references ─────────────────────────────────────────
        if references:
            build_references(references, pe)

        # ── Taxes & Charges tab ───────────────────────────────────────────────
        if taxes:
            build_taxes(taxes, pe)

        pe.insert(ignore_permissions=True)
        pe.submit()
        frappe.db.commit()

        return old_response(
            status="success",
            message="Payment entry created successfully.",
            data={
                "paymentId":       pe.name,
                "paymentType":     pe.payment_type,
                "partyType":       pe.party_type,
                "partyName":       pe.party,
                "paidFrom":        pe.paid_from,
                "paidTo":          pe.paid_to,
                "paidAmount":      pe.paid_amount,
                "receivedAmount":  pe.received_amount,
                "paymentDate":     str(pe.posting_date),
                "referenceNo":     pe.reference_no,
                "status":          pe.status,
            },
            status_code=201,
            http_status=201
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Payment Entry API Error")
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        
        frappe.db.rollback()

        return old_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )

# ─────────────────────────────────────────
# GET ALL PAYMENTS
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_all_payments():
    try:
        args = frappe.request.args

        page = args.get("page", 1)
        page_size = args.get("page_size", 10)

        try:
            page = int(page)
            if page < 1:
                raise ValueError
        except ValueError:
            return send_response(
                status="error",
                message="'page' must be a positive integer.",
                data=None,
                status_code=400,
                http_status=400,
            )

        try:
            page_size = int(page_size)
            if page_size < 1:
                raise ValueError
        except ValueError:
            return send_response(
                status="error",
                message="'page_size' must be a positive integer.",
                data=None,
                status_code=400,
                http_status=400,
            )

        start_index = (page - 1) * page_size

        # ─────────────────────────────────────────
        # FILTERS
        # ─────────────────────────────────────────
        filters = {}
        or_filters = []

        payment_type = args.get("paymentType")
        if payment_type:
            payment_type = payment_type.lower()
            if payment_type == "receive":
                filters["payment_type"] = "Receive"
            elif payment_type == "pay":
                filters["payment_type"] = "Pay"

        # Party filter (Customer or Supplier)
        party_type = args.get("partyType")
        if party_type:
            filters["party_type"] = party_type

        partyName = args.get("partyName")
        party_type = args.get("partyType")  # "Customer" or "Supplier"
        if partyName and party_type:
            if party_type == "Customer":
                party_name = frappe.db.get_value(
                    "Customer", {"customer_name": partyName}, "name"
                )
            elif party_type == "Supplier":
                party_name = frappe.db.get_value(
                    "Supplier", {"supplier_name": partyName}, "name"
                )
            else:
                party_name = None

            if not party_name:
                return send_response(
                    status="error",
                    message=f"{party_type} with ID '{partyName}' not found.",
                    data=None,
                    status_code=404,
                    http_status=404,
                )
            filters["party_type"] = party_type
            filters["party"] = party_name

        # Payment mode filter
        payment_mode = args.get("paymentMode")
        if payment_mode:
            filters["mode_of_payment"] = ["like", f"%{payment_mode}%"]

        # Status filter
        status = args.get("status")
        if status:
            filters["status"] = status

        # Date range filter
        from_date = args.get("from_date")
        to_date = args.get("to_date")
        if from_date and to_date:
            filters["posting_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["posting_date"] = [">=", from_date]
        elif to_date:
            filters["posting_date"] = ["<=", to_date]

        # Amount range filter
        min_amount = args.get("minAmount")
        max_amount = args.get("maxAmount")
        if min_amount and max_amount:
            filters["paid_amount"] = ["between", [float(min_amount), float(max_amount)]]
        elif min_amount:
            filters["paid_amount"] = [">=", float(min_amount)]
        elif max_amount:
            filters["paid_amount"] = ["<=", float(max_amount)]

        # Search filter
        search = args.get("search")
        if search:
            or_filters = [
                ["name", "like", f"%{search}%"],
                ["party", "like", f"%{search}%"],
                ["mode_of_payment", "like", f"%{search}%"],
                ["reference_no", "like", f"%{search}%"],
                ["party_type", "like", f"%{search}%"],
                ["payment_type", "like", f"%{search}%"],
                ["company", "like", f"%{search}%"]
            ]

            try:
                search_amount = float(search)
                or_filters.append(["paid_amount", "=", search_amount])
            except ValueError:
                pass

            # Search by date if valid date
            from datetime import datetime

            try:
                datetime.strptime(search, "%Y-%m-%d")
                or_filters.append(["posting_date", "=", search])
            except ValueError:
                pass

        # ─────────────────────────────────────────
        # SORTING
        # ─────────────────────────────────────────
        allowed_sort_fields = {
            "id": "name",
            "partyName": "party",
            "paymentDate": "posting_date",
            "amount": "paid_amount",
            "paymentMode": "mode_of_payment",
            "status": "status",
        }

        sort_by = args.get("sortBy", "paymentDate")
        sort_order = args.get("sortOrder", "desc").lower()
        sort_field = allowed_sort_fields.get(sort_by, "posting_date")
        sort_order = "asc" if sort_order == "asc" else "desc"
        order_by = f"{sort_field} {sort_order}"

        # ─────────────────────────────────────────
        # FETCH
        # ─────────────────────────────────────────
        payments = frappe.get_all(
            "Payment Entry",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name as paymentId",
                "payment_type as paymentType",
                "party_type as partyType",
                "party as partyName",
                "mode_of_payment as paymentMode",
                "posting_date as paymentDate",
                "paid_amount as amount",
                "reference_no as referenceNumber",
                "status",
            ],
            order_by=order_by,
            start=start_index,
            page_length=page_size,
        )

        total_payments = len(
            frappe.get_all(
                "Payment Entry", filters=filters, or_filters=or_filters, pluck="name"
            )
        )

        if total_payments == 0:
            return send_response(
                status="success",
                message="No payments found.",
                data=[],
                status_code=200,
                http_status=200,
            )

        total_pages = (total_payments + page_size - 1) // page_size

        response_data = {
            "payments": payments,
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": total_payments,
                "totalPages": total_pages,
                "hasNext": page < total_pages,
                "hasPrev": page > 1,
            },
        }

        return send_response_list(
            status="success",
            message="Payments fetched successfully.",
            status_code=200,
            http_status=200,
            data=response_data,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Payments API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


# ─────────────────────────────────────────
# GET PAYMENT BY ID
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_payment_by_id():
    try:
        payment_id = frappe.request.args.get("payment_id")

        if not payment_id:
            return send_response(
                status="error",
                message="Parameter 'payment_id' is required.",
                data=None,
                status_code=400,
                http_status=400,
            )

        if not frappe.db.exists("Payment Entry", payment_id):
            return send_response(
                status="error",
                message=f"Payment Entry '{payment_id}' not found.",
                data=None,
                status_code=404,
                http_status=404,
            )

        doc = frappe.get_doc("Payment Entry", payment_id)

        # 1. Map Allocations (References)
        allocations = []
        for ref in doc.get("references"):
            allocations.append(
                {
                    "reference_doctype": ref.reference_doctype,
                    "reference_name": ref.reference_name,
                    "total_amount": ref.total_amount,
                    "outstanding_amount": ref.outstanding_amount,
                    "allocated_amount": ref.allocated_amount,
                    "account": ref.account,
                }
            )

        # 2. Map Taxes
        taxes = []
        for t in doc.get("taxes"):
            taxes.append(
                {
                    "account_head": t.account_head,
                    "tax_amount": t.tax_amount,
                    "description": t.description,
                    "rate": t.rate,
                }
            )

        # 3. Map Deductions
        deductions = []
        for d in doc.get("deductions"):
            deductions.append(
                {"account": d.account, "amount": d.amount, "description": d.description}
            )

        detailed_data = {
            "header": {
                "payment_id": doc.name,
                "payment_type": doc.payment_type,
                "status": doc.status,
                "posting_date": doc.posting_date,
                "company": doc.company,
                "naming_series": doc.naming_series,
            },
            "party_info": {
                "party_type": doc.party_type,
                "party": doc.party,
                "party_name": doc.party_name,
                "contact_person": doc.contact_person,
                "contact_email": doc.contact_email,
            },
            "transaction_info": {
                "mode_of_payment": doc.mode_of_payment,
                "paid_from": doc.paid_from,
                "paid_from_currency": doc.paid_from_account_currency,
                "paid_to": doc.paid_to,
                "paid_to_currency": doc.paid_to_account_currency,
                "bank": doc.bank,
                "bank_account_no": doc.bank_account_no,
                "party_bank_account": doc.party_bank_account,
                "reference_no": doc.reference_no,
                "reference_date": doc.reference_date,
                "clearance_date": doc.clearance_date,
                "cost_center": doc.cost_center,
                "project": doc.project,
            },
            "amounts": {
                "paid_amount": doc.paid_amount,
                "received_amount": doc.received_amount,
                "base_paid_amount": doc.base_paid_amount,
                "base_received_amount": doc.base_received_amount,
                "total_allocated_amount": doc.total_allocated_amount,
                "unallocated_amount": doc.unallocated_amount,
                "difference_amount": doc.difference_amount,
                "source_exchange_rate": doc.source_exchange_rate,
                "target_exchange_rate": doc.target_exchange_rate,
                "amount_in_words": doc.in_words,
            },
            "allocations": allocations,
            "taxes": taxes,
            "deductions": deductions,
            "remarks": doc.remarks,
        }

        return send_response(
            status="success",
            message="Payment Entry details fetched successfully.",
            data=detailed_data,
            status_code=200,
            http_status=200,
        )

    except frappe.PermissionError:
        frappe.log_error(frappe.get_traceback(), "Get Payment By ID Permission Error")
        return send_response(
            status="error",
            message="You do not have permission to view this Payment Entry.",
            data=None,
            status_code=403,
            http_status=403,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Payment By ID API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )
