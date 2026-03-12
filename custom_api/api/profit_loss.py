import frappe
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import execute
from custom_api.utils.response import send_response


def _format_currency(value):
    """Normalize currency values to positive floats with a sign flag."""
    if value is None:
        return 0.0
    return round(float(value), 2)


def _build_tree(raw_data, period_key):
    """
    Convert flat ERPNext P&L rows into a nested income/expense tree.
    Skips summary rows (those whose account name starts with "'").
    """
    # Index rows by account key for parent-child linking
    row_map = {}
    roots = {"income": [], "expense": []}

    for row in raw_data:
        if not row or not row.get("account"):
            continue
        account = row.get("account", "")
        # Skip synthetic summary rows injected by ERPNext
        if account.startswith("'"):
            continue

        node = {
            "id": account,
            "name": row.get("account_name", account),
            "parent": row.get("parent_account") or None,
            "indent": int(row.get("indent", 0)),
            "is_group": bool(row.get("is_group", False)),
            "account_type": row.get("account_type", ""),
            "amount": _format_currency(row.get(period_key, 0)),
            "opening_balance": _format_currency(row.get("opening_balance", 0)),
            "children": [],
        }
        row_map[account] = node

    # Wire up parent-child relationships
    for node in row_map.values():
        parent_id = node["parent"]
        if parent_id and parent_id in row_map:
            row_map[parent_id]["children"].append(node)
        else:
            # Classify root nodes
            acct_id_lower = node["id"].lower()
            if "income" in acct_id_lower or "revenue" in acct_id_lower:
                roots["income"].append(node)
            else:
                roots["expense"].append(node)

    return roots


def _build_summary(report_summary):
    """Return a clean key-value summary dict from ERPNext's report_summary list."""
    summary = {}
    label_map = {
        "Total Income This Year": "total_income",
        "Total Expense This Year": "total_expense",
        "Profit This Year": "net_profit",
        "Loss This Year": "net_loss",
    }
    for item in (report_summary or []):
        label = item.get("label", "")
        key = label_map.get(label)
        if key:
            summary[key] = {
                "label": label,
                "value": _format_currency(item.get("value", 0)),
                "currency": item.get("currency", "INR"),
                "indicator": item.get("indicator", ""),  # "Green" / "Red"
            }
    return summary


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_profit_and_loss():
    company = frappe.defaults.get_user_default("Company")
    from_date = frappe.request.args.get("from_date")
    to_date = frappe.request.args.get("to_date")

    filters = frappe._dict({
        "company": company,
        "from_fiscal_year": None,
        "to_fiscal_year": None,
        "period_start_date": from_date,
        "period_end_date": to_date,
        "filter_based_on": "Date Range",
        "periodicity": "Yearly",
        "accumulated_values": 0,
    })

    columns, data, message, chart, report_summary, primitive_summary = execute(filters)

    # Identify the period column key (e.g. "dec_2026") from columns dynamically
    period_key = None
    for col in (columns or []):
        fieldname = col.get("fieldname", "")
        if fieldname not in ("account", "currency", "opening_balance", "closing_balance"):
            period_key = fieldname
            break  # Take first non-meta column as the active period

    tree = _build_tree(data, period_key) if period_key else {"income": [], "expense": []}
    summary = _build_summary(report_summary)

    is_profitable = (
        summary.get("net_profit", {}).get("value", 0) > 0
        if "net_profit" in summary
        else summary.get("net_loss", {}).get("value", 0) < 0
    )

    return send_response(
        status="success",
        message="Profit and Loss fetched successfully.",
        data={
            "meta": {
                "company": company,
                "from_date": from_date,
                "to_date": to_date,
                "currency": "INR",
                "period_key": period_key,
                "is_profitable": is_profitable,
            },
            "summary": summary,
            "income": tree["income"],
            "expense": tree["expense"],
        },
        status_code=200,
        http_status=200,
    )