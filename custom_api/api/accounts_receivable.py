import math
import hashlib
import json
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


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_accounts_receivable():
    try:
        group_by = _get_arg("group_by", "none")
        search_term = _get_arg("search", "").strip().lower()
        status_filter = (_get_arg("status") or "").strip().lower()

        if status_filter in ("", "all", "none"):
            status_filter = None

        voucher_type_filters = _get_list_arg("voucher_type")
        if voucher_type_filters:
            voucher_type_filters = [
                str(v).strip().lower() for v in voucher_type_filters
            ]

        page = int(_get_arg("page", 1))
        page_size = int(_get_arg("page_size", 10))

        filters = frappe._dict(
            {
                "company": frappe.defaults.get_user_default("Company"),
                "report_date": _get_arg("report_date", today()),
                "cost_center": _get_arg("cost_center"),
                "party_account": _get_arg("receivable_account"),
                "party_type": _get_arg("party_type"),
                "party": _get_list_arg("party"),
                "customer_group": _get_arg("customer_group"),
                "ageing_based_on": _get_arg("ageing_based_on", "Due Date"),
                "calculate_ageing_with": _get_arg(
                    "calculate_ageing_with", "Today Date"
                ),
                "range": _get_arg("range", "30, 60, 90, 120"),
                "group_by_party": 1 if group_by == "customer" else 0,
                "ignore_accounts": 1 if group_by == "voucher" else 0,
            }
        )
        filters = frappe._dict({k: v for k, v in filters.items() if v is not None})

        cache_params = {
            "user": frappe.session.user,
            "filters": filters,
            "page": page,
            "page_size": page_size,
            "search": search_term,
            "status": status_filter,
            "v_type": voucher_type_filters,
        }

        cache_key_hash = hashlib.md5(
            json.dumps(cache_params, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        cache_key = f"custom_api:ar_report:{cache_key_hash}"

        cached_response = frappe.cache().get_value(cache_key)
        if cached_response:
            return send_response(**cached_response)

        columns, raw_data, message, chart, report_summary, skip_total_row = execute(
            filters
        )

        today_date = getdate(today())
        processed_rows = []

        kpi_totals = {
            "outstanding": 0,
            "invoiced": 0,
            "paid": 0,
            "invoices_count": 0,
            "overdue_amt": 0,
            "overdue_count": 0,
            "age_days": 0,
            "age_rows": 0,
            "this_week_amt": 0,
            "this_week_count": 0,
            "week_2_amt": 0,
            "week_2_count": 0,
            "week_3_amt": 0,
            "week_3_count": 0,
            "week_4_amt": 0,
            "week_4_count": 0,
            "a_0_30": 0,
            "a_31_60": 0,
            "a_61_90": 0,
            "a_91_120": 0,
            "a_121_above": 0,
        }
        customer_totals = {}

        for row in raw_data:
            if (
                not isinstance(row, dict)
                or str(row.get("party", "")).lower() == "total"
                or (row.get("bold") and not row.get("party"))
            ):
                continue

            if not row.get("voucher_no"):
                if status_filter or search_term or voucher_type_filters:
                    continue
                if row.get("party") or row.get("customer_name"):
                    processed_rows.append(row)
                continue

            voucher_type = row.get("voucher_type", "")
            if (
                voucher_type_filters
                and str(voucher_type).lower() not in voucher_type_filters
            ):
                continue

            outstanding = _format_currency(row.get("outstanding"))
            paid = _format_currency(row.get("paid"))
            due_date_str = row.get("due_date")

            if outstanding <= 0:
                row_status = "Paid"
            elif due_date_str and getdate(due_date_str) < today_date:
                row_status = "Overdue"
            elif paid > 0:
                row_status = "Partially Paid"
            else:
                row_status = "Pending"

            if status_filter and row_status.lower() != status_filter:
                continue

            if search_term:
                customer_str = str(row.get("party", "") or "").lower()
                voucher_str = str(row.get("voucher_no", "") or "").lower()
                if search_term not in customer_str and search_term not in voucher_str:
                    continue

            is_return = row.get("is_return")
            invoiced = _format_currency(row.get("invoiced"))
            age = row.get("age") or 0

            if voucher_type == "Sales Invoice":
                if is_return:
                    kpi_totals["paid"] += abs(invoiced)
                else:
                    kpi_totals["invoiced"] += invoiced
                    kpi_totals["invoices_count"] += 1
            elif voucher_type in ["Payment Entry", "Journal Entry"]:
                kpi_totals["paid"] += paid

            kpi_totals["outstanding"] += outstanding

            if due_date_str and outstanding > 0:
                days_to_due = date_diff(getdate(due_date_str), today_date)
                if days_to_due < 0:
                    kpi_totals["overdue_amt"] += outstanding
                    kpi_totals["overdue_count"] += 1
                elif 0 <= days_to_due <= 7:
                    kpi_totals["this_week_amt"] += outstanding
                    kpi_totals["this_week_count"] += 1
                elif 8 <= days_to_due <= 14:
                    kpi_totals["week_2_amt"] += outstanding
                    kpi_totals["week_2_count"] += 1
                elif 15 <= days_to_due <= 21:
                    kpi_totals["week_3_amt"] += outstanding
                    kpi_totals["week_3_count"] += 1
                elif 22 <= days_to_due <= 30:
                    kpi_totals["week_4_amt"] += outstanding
                    kpi_totals["week_4_count"] += 1

            kpi_totals["a_0_30"] += _format_currency(row.get("range1"))
            kpi_totals["a_31_60"] += _format_currency(row.get("range2"))
            kpi_totals["a_61_90"] += _format_currency(row.get("range3"))
            kpi_totals["a_91_120"] += _format_currency(row.get("range4"))
            kpi_totals["a_121_above"] += _format_currency(row.get("range5"))

            if age:
                kpi_totals["age_days"] += age
                kpi_totals["age_rows"] += 1

            customer = row.get("customer_name") or row.get("party") or "Unknown"
            customer_totals[customer] = customer_totals.get(customer, 0) + outstanding

            processed_rows.append(
                {
                    "posting_date": row.get("posting_date"),
                    "customer": customer,
                    "party_type": row.get("party_type"),
                    "receivable_account": row.get("party_account"),
                    "voucher_type": voucher_type,
                    "voucher_no": row.get("voucher_no"),
                    "due_date": due_date_str,
                    "po_no": row.get("po_no"),
                    "cost_center": row.get("cost_center"),
                    "status": row_status,
                    "currency": row.get("currency"),
                    "territory": row.get("territory"),
                    "customer_group": row.get("customer_group"),
                    "customer_contact": row.get("customer_primary_contact"),
                    "amounts": {
                        "invoiced": invoiced,
                        "paid": paid,
                        "credit_note": _format_currency(row.get("credit_note")),
                        "outstanding": outstanding,
                    },
                    "age": age,
                    "ageing": {
                        "0_30": _format_currency(row.get("range1")),
                        "31_60": _format_currency(row.get("range2")),
                        "61_90": _format_currency(row.get("range3")),
                        "91_120": _format_currency(row.get("range4")),
                        "121_above": _format_currency(row.get("range5")),
                    },
                }
            )

        avg_collection_days = (
            kpi_totals["age_days"] / kpi_totals["age_rows"]
            if kpi_totals["age_rows"]
            else 0
        )
        avg_invoice = (
            kpi_totals["invoiced"] / kpi_totals["invoices_count"]
            if kpi_totals["invoices_count"]
            else 0
        )
        top_customers = sorted(
            customer_totals.items(), key=lambda x: x[1], reverse=True
        )[:5]

        final_kpis = {
            "total_outstanding": kpi_totals["outstanding"],
            "total_invoiced": kpi_totals["invoiced"],
            "total_paid": kpi_totals["paid"],
            "total_customers": len(customer_totals),
            "total_invoices": kpi_totals["invoices_count"],
            "overdue_amount": kpi_totals["overdue_amt"],
            "overdue_invoices": kpi_totals["overdue_count"],
            "average_invoice_amount": _format_currency(avg_invoice),
            "average_collection_days": round(avg_collection_days, 2),
            "ageing_summary": {
                "0_30": kpi_totals["a_0_30"],
                "31_60": kpi_totals["a_31_60"],
                "61_90": kpi_totals["a_61_90"],
                "91_120": kpi_totals["a_91_120"],
                "121_above": kpi_totals["a_121_above"],
            },
            "payment_schedule": {
                "this_week": {
                    "amount": _format_currency(kpi_totals["this_week_amt"]),
                    "count": kpi_totals["this_week_count"],
                },
                "week_2": {
                    "amount": _format_currency(kpi_totals["week_2_amt"]),
                    "count": kpi_totals["week_2_count"],
                },
                "week_3": {
                    "amount": _format_currency(kpi_totals["week_3_amt"]),
                    "count": kpi_totals["week_3_count"],
                },
                "week_4_plus": {
                    "amount": _format_currency(kpi_totals["week_4_amt"]),
                    "count": kpi_totals["week_4_count"],
                },
            },
            "top_customers": [
                {"customer": c, "outstanding": _format_currency(v)}
                for c, v in top_customers
            ],
        }

        total_items = len(processed_rows)
        total_pages = math.ceil(total_items / page_size) if page_size else 1
        start = (page - 1) * page_size
        end = start + page_size
        paginated_rows = processed_rows[start:end]

        response_payload = {
            "status": "success",
            "message": "Accounts Receivable fetched successfully.",
            "data": {
                "kpis": final_kpis,
                "data": paginated_rows,
                "summary": report_summary,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "items_in_page": len(paginated_rows),
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_previous": page > 1,
                },
            },
            "status_code": 200,
            "http_status": 200,
        }

        frappe.cache().set_value(cache_key, response_payload, expires_in_sec=600)

        return send_response(**response_payload)

    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(), title="Accounts Receivable API Error"
        )
        return send_response(
            status="error",
            message=f"Failed to fetch Accounts Receivable: {str(e)}",
            status_code=500,
            http_status=500,
        )
