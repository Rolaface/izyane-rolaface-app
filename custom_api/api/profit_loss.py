import frappe
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import execute
from custom_api.utils.response import send_response

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
        if col.get("fieldname") and col.get("fieldname") not in meta_fields and col.get("fieldtype") in ("Currency", "Float")
    ]

def _build_tree(raw_data, period_keys):
    row_map = {}
    roots = {"income": [], "expense": []}

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
            acct_id_lower = node["account"].lower()
            if "income" in acct_id_lower or "revenue" in acct_id_lower:
                roots["income"].append(node)
            else:
                roots["expense"].append(node)

    return roots

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_profit_and_loss():
    company = frappe.defaults.get_user_default("Company")
    current_year = frappe.utils.now_datetime().year
    from_date = frappe.request.args.get("from_date", None)
    to_date = frappe.request.args.get("to_date", None)
    periodicity = frappe.request.args.get("periodicity", "Yearly")
    from_fiscal_year = frappe.request.args.get("from_fiscal_year", current_year)
    to_fiscal_year = frappe.request.args.get("to_fiscal_year", current_year)
    filter_based_on = frappe.request.args.get("filter_based_on", "Fiscal Year")

    filters = frappe._dict({
        "company": company,
        "from_fiscal_year": from_fiscal_year,
        "to_fiscal_year": to_fiscal_year,
        "period_start_date": from_date,
        "period_end_date": to_date,
        "filter_based_on": filter_based_on,
        "periodicity": periodicity,
        "accumulated_values": 0,
    })

    columns, data, message, chart, report_summary, primitive_summary = execute(filters)

    period_keys = _detect_period_keys(columns)
    tree = _build_tree(data, period_keys) if period_keys else {"income": [], "expense": []}

    return send_response(
        status="success",
        message="Profit and Loss fetched successfully.",
        data={
            "columns": columns,
            "summary": report_summary,
            "income": tree["income"],
            "expense": tree["expense"],
        },
        status_code=200,
        http_status=200,
    )