import frappe
from erpnext.accounts.report.balance_sheet.balance_sheet import execute
from custom_api.utils.response import send_response

def _format_currency(value):
    if value is None:
        return 0.0
    return round(float(value), 2)

def _detect_period_key(columns):
    """Pick the first non-meta column as the active period key (e.g. 'dec_2026')."""
    meta_fields = {"account", "currency", "opening_balance", "closing_balance"}
    for col in (columns or []):
        fieldname = col.get("fieldname", "")
        if fieldname and fieldname not in meta_fields:
            return fieldname
    return None

def _build_tree(raw_data, period_key):
    """
    Convert ERPNext's flat rows into nested trees bucketed by section.

    ERPNext Balance Sheet root account names (account_name field):
      - "Application of Funds (Assets)"  → assets
      - "Source of Funds (Liabilities)"  → liabilities
      - Anything else (equity, capital)  → equity

    Skips synthetic summary rows whose account key starts with "'".
    """
    row_map = {}
    roots = {"assets": [], "liabilities": [], "equity": []}

    for row in raw_data:
        if not row or not row.get("account"):
            continue
        account = row.get("account", "")
        if account.startswith("'"):   # skip synthetic rows like "'Total Asset (Debit)'"
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
            "currency": row.get("currency") or None,
            "children": [],
        }
        row_map[account] = node

    # Wire parent → child relationships
    for node in row_map.values():
        parent_id = node["parent"]
        if parent_id and parent_id in row_map:
            row_map[parent_id]["children"].append(node)
        else:
            # Classify root nodes by their account name (ERPNext standard naming)
            name_lower = node["name"].lower()
            if "application of funds" in name_lower or "asset" in name_lower:
                roots["assets"].append(node)
            elif "source of funds" in name_lower or "liabilit" in name_lower:
                roots["liabilities"].append(node)
            else:
                roots["equity"].append(node)

    return roots

def _build_summary(report_summary):
    """
    Map ERPNext's flat summary list to a clean dict.
    Actual labels from the API response:
      "Total Asset", "Total Liability", "Total Equity",
      "Provisional Profit / Loss (Credit)"
    """
    summary = {}
    label_map = {
        "Total Asset":                          "total_assets",
        "Total Liability":                      "total_liabilities",
        "Total Equity":                         "total_equity",
        "Provisional Profit / Loss (Credit)":   "provisional_profit_loss",
        # Fallbacks for other ERPNext versions
        "Total Assets":                         "total_assets",
        "Total Liabilities":                    "total_liabilities",
        "Difference (Assets - Liabilities)":    "difference",
    }
    for item in (report_summary or []):
        if item.get("type") == "separator":
            continue
        label = item.get("label", "")
        key = label_map.get(label)
        if key:
            summary[key] = {
                "label": label,
                "value": _format_currency(item.get("value", 0)),
                "currency": item.get("currency", "INR"),
                "indicator": item.get("indicator", ""),
            }
    return summary


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_balance_sheet():
    """
    GET /api/method/custom_api.your_module.get_balance_sheet
    Query Params:
        from_date   (str, required) – e.g. "2026-01-01"
        to_date     (str, required) – e.g. "2026-12-31"
    """
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

    period_key = _detect_period_key(columns)
    tree = _build_tree(data, period_key) if period_key else {"assets": [], "liabilities": [], "equity": []}
    summary = _build_summary(report_summary)

    total_assets     = summary.get("total_assets", {}).get("value", 0.0)
    total_liabilities = summary.get("total_liabilities", {}).get("value", 0.0)
    total_equity     = summary.get("total_equity", {}).get("value", 0.0)
    provisional_pl   = summary.get("provisional_profit_loss", {}).get("value", 0.0)

    # Assets should equal Liabilities + Equity + Provisional P&L
    difference = round(total_assets - (total_liabilities + total_equity + provisional_pl), 2)

    return send_response(
        status="success",
        message="Balance Sheet fetched successfully.",
        data={
            "summary": summary,
            "assets": tree["assets"],
            "liabilities": tree["liabilities"],
            "equity": tree["equity"],
        },
        status_code=200,
        http_status=200,
    )