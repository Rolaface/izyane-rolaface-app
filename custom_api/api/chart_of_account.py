import frappe
from custom_api.utils.response import send_response

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
        for acc in accounts:
            balance_data = balance_map.get(acc["name"])
            if balance_data:
                raw_balance = balance_data["balance"]
                acc["account_currency"] = balance_data["account_currency"]

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

        return send_response(
            status="success",
            message="Chart of accounts fetched successfully.",
            data={
                "company": company,
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