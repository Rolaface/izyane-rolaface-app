import frappe
from frappe.desk.query_report import run
from custom_api.utils.response import send_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_trial_balance():
    company = frappe.defaults.get_user_default("Company")

    from_date = frappe.request.args.get("from_date")
    to_date = frappe.request.args.get("to_date")
    show_zero_balances = frappe.request.args.get("show_zero_balances", "0") == "1"
    fiscal_year = frappe.request.args.get("fiscal_year")
    with_period_closing_entry = frappe.request.args.get("with_period_closing_entry", "0")
    show_closing_entries = frappe.request.args.get("show_closing_entries","0")
    empty_response = {
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "total_accounts": 0,
        "totals": {
            "opening_debit": 0.0,
            "opening_credit": 0.0,
            "debit": 0.0,
            "credit": 0.0,
            "closing_debit": 0.0,
            "closing_credit": 0.0,
        },
        "accounts": []
    }

    try:
        if not from_date or not to_date:
            return send_response(
                status="error",
                message="'from_date' and 'to_date' are required query params.",
                data=None,
                status_code=400,
                http_status=400
            )

        filters = {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
            "show_zero_values": show_zero_balances,
            "with_period_closing_entry": with_period_closing_entry,
            "show_closing_entries": show_closing_entries,
            "fiscal_year": fiscal_year,
        }

        result = run(
            "Trial Balance",
            filters=filters,
            user=frappe.session.user
        )

        data = result.get("result", [])

        # ── Clean data: remove total row and invalid entries ───────────────
        cleaned_data = [
            row for row in data
            if isinstance(row, dict)
            and row.get("account")
            and "'Total'" not in str(row.get("account"))
        ]

        # ── Compute totals from ledger accounts only ───────────────────────
        totals = {
            "opening_debit": 0.0,
            "opening_credit": 0.0,
            "debit": 0.0,
            "credit": 0.0,
            "closing_debit": 0.0,
            "closing_credit": 0.0,
        }
        for row in cleaned_data:
            if not row.get("is_group"):
                totals["opening_debit"]  += row.get("opening_debit", 0) or 0
                totals["opening_credit"] += row.get("opening_credit", 0) or 0
                totals["debit"]          += row.get("debit", 0) or 0
                totals["credit"]         += row.get("credit", 0) or 0
                totals["closing_debit"]  += row.get("closing_debit", 0) or 0
                totals["closing_credit"] += row.get("closing_credit", 0) or 0

        # ── Build tree ─────────────────────────────────────────────────────
        def build_tree(rows, parent=None):
            tree = []
            for row in rows:
                row_parent = row.get("parent_account")
                if row_parent == parent:
                    children = build_tree(rows, parent=row["account"])
                    node = {
                        "account": row.get("account"),
                        "account_name": row.get("account_name"),
                        "currency": row.get("currency"),
                        "indent": row.get("indent"),
                        "opening_debit": round(row.get("opening_debit", 0) or 0, 2),
                        "opening_credit": round(row.get("opening_credit", 0) or 0, 2),
                        "debit": round(row.get("debit", 0) or 0, 2),
                        "credit": round(row.get("credit", 0) or 0, 2),
                        "closing_debit": round(row.get("closing_debit", 0) or 0, 2),
                        "closing_credit": round(row.get("closing_credit", 0) or 0, 2),
                        "has_value": row.get("has_value", False),
                    }
                    if children:
                        node["children"] = children
                    else:
                        node["children"] = []
                    tree.append(node)
            return tree

        tree = build_tree(cleaned_data, parent=None)

        return send_response(
            status="success",
            message="Trial balance fetched successfully.",
            data={
                "company": company,
                "from_date": from_date,
                "to_date": to_date,
                "total_accounts": len(cleaned_data),
                "totals": {k: round(v, 2) for k, v in totals.items()},
                "accounts": tree,
            },
            status_code=200,
            http_status=200
        )

    except (frappe.DoesNotExistError, frappe.ValidationError) as e:
        # ── Handles "Fiscal Year XXXX does not exist" and similar ──────────
        return send_response(
            status="success",
            message="Trial balance fetched successfully.",
            data=empty_response,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Trial Balance API Error")
        return send_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )