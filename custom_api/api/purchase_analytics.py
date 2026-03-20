import math
import frappe
from frappe.utils import today, getdate

from erpnext.buying.report.purchase_analytics.purchase_analytics import execute
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


def _calculate_purchase_kpis(rows):
    total_value = 0
    entity_totals = {}

    for r in rows:
        entity = r.get("entity_name") or r.get("entity") or "Unknown"
        row_total = _format_currency(r.get("total"))

        total_value += row_total
        entity_totals[entity] = row_total

    top_entities = sorted(entity_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total_purchase_value": _format_currency(total_value),
        "total_entities_analyzed": len(rows),
        "average_value_per_entity": (
            _format_currency(total_value / len(rows)) if len(rows) else 0.0
        ),
        "top_performers": [
            {"entity": e, "total_value": _format_currency(v)} for e, v in top_entities
        ],
    }


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_purchase_analytics():
    filters = frappe._dict(
        {
            "tree_type": _get_arg("tree_type", "Supplier"),
            "doc_type": _get_arg("based_on", "Purchase Invoice"),
            "value_quantity": _get_arg("value_quantity", "Value"),
            "from_date": _get_arg("from_date", f"{today()[:4]}-01-01"),
            "to_date": _get_arg("to_date", f"{today()[:4]}-12-31"),
            "company": _get_arg("company", frappe.defaults.get_user_default("Company")),
            "range": _get_arg("range", "Monthly"),
        }
    )

    filters = frappe._dict({k: v for k, v in filters.items() if v is not None})

    page = int(_get_arg("page", 1))
    page_size = int(_get_arg("page_size", 10))

    report_execution = execute(filters)
    columns = report_execution[0]
    raw_data = report_execution[1]

    chart = report_execution[3] if len(report_execution) > 3 else None
    report_summary = report_execution[4] if len(report_execution) > 4 else None

    filtered_data = []

    for row in raw_data:
        if isinstance(row, list):
            continue

        if not isinstance(row, dict):
            continue

        if not row.get("entity"):
            continue

        filtered_data.append(row)

    kpis = _calculate_purchase_kpis(filtered_data)

    total_items = len(filtered_data)
    total_pages = math.ceil(total_items / page_size) if page_size else 1

    start = (page - 1) * page_size
    end = start + page_size

    paginated_rows = filtered_data[start:end]

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
        message="Purchase Analytics fetched successfully.",
        data={
            "kpis": kpis,
            "data": paginated_rows,
            "columns": columns,
            "summary": report_summary,
            "chart": chart,
            "pagination": pagination,
        },
        status_code=200,
        http_status=200,
    )
