import math
import frappe
from frappe.utils import today, getdate, date_diff
from erpnext.accounts.report.accounts_receivable.accounts_receivable import execute
from custom_api.utils.response import send_response


def _format_currency(value):
    if value is None:
        return 0.0
    try:
        return round(float(value), 2)
    except Exception:
        return 0.0


def _get_arg(key, default=None):
    return frappe.request.args.get(key, default)


def _get_list_arg(key):
    val = frappe.request.args.get(key)
    if not val:
        return None

    try:
        parsed = frappe.parse_json(val)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    if isinstance(val, str) and "," in val:
        return [item.strip() for item in val.split(",") if item.strip()]

    return [val]


def _calculate_receivable_kpis(rows):

    total_outstanding = 0
    total_invoiced = 0
    total_paid = 0

    total_invoices = 0
    overdue_amount = 0
    overdue_invoices = 0

    ageing_0_30 = ageing_31_60 = ageing_61_90 = 0
    ageing_91_120 = ageing_121_above = 0

    customer_totals = {}

    total_age_days = 0
    counted_age_rows = 0

    # Payment Schedule Buckets
    this_week_amt = week_2_amt = week_3_amt = week_4_amt = 0
    this_week_count = week_2_count = week_3_count = week_4_count = 0

    today_date = getdate(today())

    for r in rows:

        if not isinstance(r, dict):
            continue

        if not r.get("voucher_no"):
            continue

        voucher_type = r.get("voucher_type")
        is_return = r.get("is_return")

        outstanding = _format_currency(r.get("outstanding"))
        invoiced = _format_currency(r.get("invoiced"))
        paid = _format_currency(r.get("paid"))

        due_date_str = r.get("due_date")
        age = r.get("age") or 0

        if voucher_type == "Sales Invoice":
            if is_return:
                total_paid += abs(invoiced)  # credit note
            else:
                total_invoiced += invoiced
                total_invoices += 1

        elif voucher_type in ["Payment Entry", "Journal Entry"]:
            total_paid += paid

        total_outstanding += outstanding

        # Calculate Overdue AND Future Payment Schedule
        if due_date_str and outstanding > 0:
            due_date_obj = getdate(due_date_str)
            days_to_due = date_diff(due_date_obj, today_date)

            if days_to_due < 0:
                overdue_amount += outstanding
                overdue_invoices += 1
            elif 0 <= days_to_due <= 7:
                this_week_amt += outstanding
                this_week_count += 1
            elif 8 <= days_to_due <= 14:
                week_2_amt += outstanding
                week_2_count += 1
            elif 15 <= days_to_due <= 21:
                week_3_amt += outstanding
                week_3_count += 1
            elif 22 <= days_to_due <= 30:
                week_4_amt += outstanding
                week_4_count += 1

        ageing_0_30 += _format_currency(r.get("range1"))
        ageing_31_60 += _format_currency(r.get("range2"))
        ageing_61_90 += _format_currency(r.get("range3"))
        ageing_91_120 += _format_currency(r.get("range4"))
        ageing_121_above += _format_currency(r.get("range5"))

        if age:
            total_age_days += age
            counted_age_rows += 1

        customer = r.get("customer_name") or r.get("party") or "Unknown"
        customer_totals.setdefault(customer, 0)
        customer_totals[customer] += outstanding

    avg_collection_days = total_age_days / counted_age_rows if counted_age_rows else 0
    avg_invoice = total_invoiced / total_invoices if total_invoices else 0

    top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[
        :5
    ]

    return {
        "total_outstanding": total_outstanding,
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "total_customers": len(customer_totals),
        "total_invoices": total_invoices,
        "overdue_amount": overdue_amount,
        "overdue_invoices": overdue_invoices,
        "average_invoice_amount": _format_currency(avg_invoice),
        "average_collection_days": round(avg_collection_days, 2),
        "ageing_summary": {
            "0_30": ageing_0_30,
            "31_60": ageing_31_60,
            "61_90": ageing_61_90,
            "91_120": ageing_91_120,
            "121_above": ageing_121_above,
        },
        "payment_schedule": {
            "this_week": {
                "amount": _format_currency(this_week_amt),
                "count": this_week_count,
            },
            "week_2": {"amount": _format_currency(week_2_amt), "count": week_2_count},
            "week_3": {"amount": _format_currency(week_3_amt), "count": week_3_count},
            "week_4_plus": {
                "amount": _format_currency(week_4_amt),
                "count": week_4_count,
            },
        },
        "top_customers": [
            {"customer": c, "outstanding": _format_currency(v)}
            for c, v in top_customers
        ],
    }


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_accounts_receivable():

    group_by = _get_arg("group_by", "none")
    search_term = _get_arg("search", "").strip().lower()
    status_filter = (_get_arg("status") or "").strip().lower()

    if status_filter in ("", "all", "none"):
        status_filter = None

    voucher_type_filters = _get_list_arg("voucher_type")
    if voucher_type_filters:
        voucher_type_filters = [str(v).strip().lower() for v in voucher_type_filters]

    filters = frappe._dict(
        {
            "company": frappe.defaults.get_user_default("Company"),
            "report_date": _get_arg("report_date", today()),
            "cost_center": _get_list_arg("cost_center"),
            "party_account": _get_list_arg("receivable_account"),
            "party_type": _get_arg("party_type"),
            "party": _get_list_arg("party"),
            "customer_group": _get_list_arg("customer_group"),
            "ageing_based_on": _get_arg("ageing_based_on", "Due Date"),
            "calculate_ageing_with": _get_arg("calculate_ageing_with", "Today Date"),
            "range": _get_arg("range", "30, 60, 90, 120"),
            "group_by_party": 1 if group_by == "customer" else 0,
            "ignore_accounts": 1 if group_by == "voucher" else 0,
        }
    )

    filters = frappe._dict({k: v for k, v in filters.items() if v is not None})

    page = int(_get_arg("page", 1))
    page_size = int(_get_arg("page_size", 10))

    columns, raw_data, message, chart, report_summary, skip_total_row = execute(filters)

    filtered_data = []
    today_date = getdate(today())

    for row in raw_data:
        if not isinstance(row, dict):
            continue

        if str(row.get("party", "")).lower() == "total" or (
            row.get("bold") and not row.get("party")
        ):
            continue

        if row.get("voucher_no"):

            if (
                voucher_type_filters
                and str(row.get("voucher_type", "")).lower() not in voucher_type_filters
            ):
                continue

            outstanding = _format_currency(row.get("outstanding"))
            paid = _format_currency(row.get("paid"))
            due_date = row.get("due_date")

            if outstanding <= 0:
                row_status = "Paid"
            elif due_date and getdate(due_date) < today_date:
                row_status = "Overdue"
            elif paid > 0:
                row_status = "Partially Paid"
            else:
                row_status = "Pending"

            row["payment_status"] = row_status

            if status_filter and row_status.lower() != status_filter:
                continue

            if search_term:
                customer = str(row.get("party") or "").lower()
                voucher_no = str(row.get("voucher_no", "") or "").lower()

                if search_term not in customer and search_term not in voucher_no:
                    continue
        else:
            if status_filter or search_term or voucher_type_filters:
                continue

        filtered_data.append(row)

    kpis = _calculate_receivable_kpis(filtered_data)

    rows = []

    for row in filtered_data:
        rows.append(
            {
                "posting_date": row.get("posting_date"),
                "customer": row.get("party"),
                "party_type": row.get("party_type"),
                "receivable_account": row.get("party_account"),
                "voucher_type": row.get("voucher_type"),
                "voucher_no": row.get("voucher_no"),
                "due_date": row.get("due_date"),
                "po_no": row.get("po_no"),
                "cost_center": row.get("cost_center"),
                "status": row.get("payment_status"),
                "currency": row.get("currency"),
                "territory": row.get("territory"),
                "customer_group": row.get("customer_group"),
                "customer_contact": row.get("customer_primary_contact"),
                "amounts": {
                    "invoiced": _format_currency(row.get("invoiced")),
                    "paid": _format_currency(row.get("paid")),
                    "credit_note": _format_currency(row.get("credit_note")),
                    "outstanding": _format_currency(row.get("outstanding")),
                },
                "age": row.get("age"),
                "ageing": {
                    "0_30": _format_currency(row.get("range1")),
                    "31_60": _format_currency(row.get("range2")),
                    "61_90": _format_currency(row.get("range3")),
                    "91_120": _format_currency(row.get("range4")),
                    "121_above": _format_currency(row.get("range5")),
                },
            }
        )

    total_items = len(rows)
    total_pages = math.ceil(total_items / page_size) if page_size else 1

    start = (page - 1) * page_size
    end = start + page_size

    paginated_rows = rows[start:end]

    pagination = {
        "page": page,
        "page_size": page_size,
        "items_in_page": len(paginated_rows),
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }

    return send_response(
        status="success",
        message="Accounts Receivable fetched successfully.",
        data={
            "kpis": kpis,
            "data": paginated_rows,
            "summary": report_summary,
            "pagination": pagination,
        },
        status_code=200,
        http_status=200,
    )
