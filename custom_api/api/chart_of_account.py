from erpnext.accounts.utils import get_balance_on
import frappe
import math
from frappe.utils import flt
from custom_api.utils.response import send_response
from erpnext.accounts.report.general_ledger.general_ledger import execute 

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

def rollup_balances(nodes):
    for node in nodes:
        if node.get("children"):
            rollup_balances(node["children"])
            # Sum children balances into parent
            node["balance"] = round(
                sum(child.get("balance", 0.0) for child in node["children"]), 2)
    return nodes

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_chart_of_accounts():
    try:
        company = frappe.defaults.get_user_default("Company")
        
        filters = {"company": company}
        
        account_type = frappe.request.args.get("account_type")
        root_type = frappe.request.args.get("root_type")
        is_group = frappe.request.args.get("is_group")
        parent_account = frappe.request.args.get("parent_account")

        if account_type:
            filters["account_type"] = account_type
        if root_type:
            filters["root_type"] = root_type
        if is_group is not None:
            filters["is_group"] = int(is_group)
        if parent_account:
            filters["parent_account"] = parent_account

        accounts = frappe.get_all(
            "Account",
            filters=filters,
            fields=[
                "name",
                "account_name",
                "account_number",
                "parent_account",
                "account_type",
                "root_type",
                "is_group",
                "account_currency",
                "disabled"
            ],
            order_by="lft asc"
        )

        if not accounts:
            return send_response(
                status="success",
                message="No accounts found.",
                data=[],
                status_code=200,
                http_status=200
            )

        # ── Fetch balances for all accounts in ONE query ───────────────────
        account_names = [acc["name"] for acc in accounts]

        balances_raw = frappe.db.sql("""
            SELECT
                account,
                SUM(debit) - SUM(credit) AS balance,
                account_currency
            FROM `tabGL Entry`
            WHERE
                account IN %(accounts)s
                AND company = %(company)s
                AND is_cancelled = 0
            GROUP BY account, account_currency
        """, {
            "accounts": account_names,
            "company": company
        }, as_dict=True)

        # ── Map balances by account name ───────────────────────────────────
        balance_map = {}
        for row in balances_raw:
            balance_map[row["account"]] = {
                "balance": row["balance"],
                "account_currency": row["account_currency"]
            }

        # ── Attach balance and currency to each account ────────────────────
        company_currency = frappe.get_cached_value("Company", company, "default_currency")

        for acc in accounts:
            balance_data = balance_map.get(acc["name"])
            if balance_data:
                raw_balance = balance_data["balance"]
                acc["account_currency"] = balance_data["account_currency"]
                if acc["account_currency"] and acc["account_currency"] != company_currency:
                    acc["balance_in_account_currency"] = flt(get_balance_on(acc["name"], company=company))

                # ── For liability/equity/income: credit is positive ────────
                if acc.get("root_type") in ("Liability", "Equity", "Income"):
                    acc["balance"] = -raw_balance   # flip sign → positive means credit balance
                else:
                    acc["balance"] = raw_balance    # Asset/Expense: debit is positive
            else:
                acc["balance"] = 0.0
                acc["account_currency"] = acc.get("currency")

        # ── Build tree ─────────────────────────────────────────────────────
        def build_tree(accounts, parent=None):
            tree = []
            for acc in accounts:
                if acc.get("parent_account") == parent:
                    acc["children"] = build_tree(accounts, parent=acc["name"])
                    tree.append(acc)
            return tree

        tree = build_tree(accounts)
        rollup_balances(tree)
        return send_response(
            status="success",
            message="Chart of accounts fetched successfully.",
            data={
                "company": company,
                "base_currency" : company_currency,
                "total": len(accounts),
                "accounts": tree
            },
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Chart of Accounts API Error")
        return send_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )   

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_general_ledger_detail():
    try:
        try:
            page = int(_get_arg("page", 1))
        except ValueError:
            page = 1

        try:
            page_size = int(_get_arg("page_size", 10))
        except ValueError:
            page_size = 10

        company = _get_arg("company") or frappe.defaults.get_user_default("Company")
        account = _get_list_arg("account")

        filters = frappe._dict({
            "company": company,
            "from_date": _get_arg("from_date"),
            "to_date": _get_arg("to_date"),
            "account": account,
            "party": _get_list_arg("party"),
            "cost_center": _get_list_arg("cost_center"),
            "project": _get_list_arg("project"),
            "include_dimensions": 1,
            "include_default_book_entries": 1
        })

        filters = frappe._dict({k: v for k, v in filters.items() if v is not None and v != [] and v != ""})

        result = execute(filters)

        if len(result) == 2:
            columns, raw_data = result
        else:
            columns, raw_data, message, chart, report_summary, skip_total_row = result

        opening = {"debit": 0, "credit": 0, "balance": 0}
        total = {"debit": 0, "credit": 0, "balance": 0}
        closing = {"debit": 0, "credit": 0, "balance": 0}
        full_ledger = []
        
        account_currency = None
        presentation_currency = None

        for row in raw_data:
            if not row or not isinstance(row, dict):
                continue

            account_raw = str(row.get("account", ""))
            account_label = account_raw.replace("'", "").strip().lower()

            account_currency = account_currency or row.get("account_currency")
            presentation_currency = presentation_currency or row.get("presentation_currency")

            if account_label == "opening":
                opening = {
                    "debit": _format_currency(row.get("debit")),
                    "credit": _format_currency(row.get("credit")),
                    "balance": _format_currency(row.get("balance")),
                }
                continue

            elif account_label == "total":
                total = {
                    "debit": _format_currency(row.get("debit")),
                    "credit": _format_currency(row.get("credit")),
                    "balance": _format_currency(row.get("balance")),
                }
                continue

            elif "closing" in account_label:
                closing = {
                    "debit": _format_currency(row.get("debit")),
                    "credit": _format_currency(row.get("credit")),
                    "balance": _format_currency(row.get("balance")),
                }
                continue

            # Skip non-ledger rows
            if not row.get("voucher_no"):
                continue

            full_ledger.append({
                "gl_entry": row.get("gl_entry"),
                "posting_date": row.get("posting_date"),
                "account": row.get("account"),
                "party_type": row.get("party_type") or "",
                "party": row.get("party") or "",
                "voucher_type": row.get("voucher_type"),
                "voucher_subtype": row.get("voucher_subtype") or "",
                "voucher_no": row.get("voucher_no"),
                "cost_center": row.get("cost_center") or "",
                "project": row.get("project") or "",
                "against_voucher_type": row.get("against_voucher_type") or "",
                "against_voucher": row.get("against_voucher") or "",
                "account_currency": row.get("account_currency"),
                "against": row.get("against") or "",
                "is_opening": row.get("is_opening") or "No",
                "creation": row.get("creation"),
                "debit": _format_currency(row.get("debit")),
                "credit": _format_currency(row.get("credit")),
                "debit_in_account_currency": _format_currency(row.get("debit_in_account_currency")),
                "credit_in_account_currency": _format_currency(row.get("credit_in_account_currency")),
                "balance": _format_currency(row.get("balance")),
                "bill_no": row.get("bill_no") or "",
                "remarks": row.get("remarks") or "No Remarks",
                "presentation_currency": row.get("presentation_currency") or ""
            })

        total_entries = len(full_ledger)
        total_pages = math.ceil(total_entries / page_size) if page_size else 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_ledger = full_ledger[start_idx:end_idx]

        response_payload = {
            "status_code": 200,
            "status": "success",
            "message": "Ledger details fetched successfully.",
            "data": {
                "account": account[0] if account else None,
                "account_currency": account_currency,
                "presentation_currency": presentation_currency,
                "company": company,
                "summary": {
                    "opening": opening,
                    "total": total,
                    "closing": closing,
                },
                "columns": columns,
                "ledger": paginated_ledger,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_entries": total_entries,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            },
        }

        return send_response(**response_payload)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "GL Execute API Error in get_general_ledger_details api")
        return send_response(
            status="error",
            message=str(e),
            status_code=500,
            http_status=500,
        )