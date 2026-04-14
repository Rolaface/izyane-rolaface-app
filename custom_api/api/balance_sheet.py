import frappe
from erpnext.accounts.report.balance_sheet.balance_sheet import execute
from custom_api.utils.response import send_response
from erpnext.accounts.utils import get_fiscal_year

def _format_currency(value):
    if isinstance(value, (int, float)):
        return round(value, 2)
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0

def _detect_period_keys(columns):
    meta_fields = {"account", "currency", "opening_balance", "closing_balance"}
    return [
        col.get("fieldname")
        for col in (columns or [])
        if col.get("fieldname") and col.get("fieldname") not in meta_fields
    ]

def _build_tree(raw_data, period_keys):
    row_map = {}
    roots = {"assets": [], "liabilities": [], "equity": []}

    for row in raw_data:
        if not row or not row.get("account"):
            continue
        account = row.get("account", "")
        if account.startswith("'"):
            continue
        periods = {key: _format_currency(row.get(key, 0)) for key in period_keys}
        node = {
            **row,
            "periods": periods,
            "total": _format_currency(row.get("total", 0)),
            "opening_balance": _format_currency(row.get("opening_balance", 0)),
            "children": [],
        }
        for key in period_keys:
            node.pop(key, None)

        row_map[account] = node

    for node in row_map.values():
        parent_id = node.get("parent_account") or ""
        if parent_id and parent_id in row_map:
            row_map[parent_id]["children"].append(node)
        else:
            name_lower = node.get("account_name", "").lower()
            if "application of funds" in name_lower or "asset" in name_lower:
                roots["assets"].append(node)
            elif "source of funds" in name_lower or "liabilit" in name_lower:
                roots["liabilities"].append(node)
            else:
                roots["equity"].append(node)

    return roots

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_balance_sheet():
    company = frappe.defaults.get_user_default("Company")
    current_year = frappe.utils.now_datetime().year
    from_date = frappe.request.args.get("from_date", None)
    to_date = frappe.request.args.get("to_date", None)
    periodicity = frappe.request.args.get("periodicity", "Yearly")
    from_fiscal_year = frappe.request.args.get("from_fiscal_year", current_year)
    to_fiscal_year = frappe.request.args.get("to_fiscal_year", current_year)

    # fy, fy_start, fy_end = get_fiscal_year(
    # frappe.utils.nowdate(),
    # company=company
    # )

    # from_fiscal_year = frappe.request.args.get("from_fiscal_year") or fy
    # to_fiscal_year = frappe.request.args.get("to_fiscal_year") or fy

    # from_date = frappe.request.args.get("from_date") or fy_start
    # to_date = frappe.request.args.get("to_date") or fy_end
    filter_based_on = frappe.request.args.get("filter_based_on", "Fiscal Year")

    filters = frappe._dict({
        "company": company,
        "from_fiscal_year": from_fiscal_year,
        "to_fiscal_year": to_fiscal_year,
        "period_start_date": from_date,
        "period_end_date": to_date,
        "filter_based_on": filter_based_on,
        "periodicity": periodicity,
        "selected_view": "Report"
    })

    columns, data, message, chart, report_summary, primitive_summary = execute(filters)
    period_keys = _detect_period_keys(columns)
    tree = _build_tree(data, period_keys) if period_keys else {"assets": [], "liabilities": [], "equity": []}

    return send_response(
        status="success",
        message="Balance Sheet fetched successfully.",
        data={
            "columns": columns,
            "summary": report_summary,
            "assets": tree["assets"],
            "liabilities": tree["liabilities"],
            "equity": tree["equity"],
        },
        status_code=200,
        http_status=200,
    )