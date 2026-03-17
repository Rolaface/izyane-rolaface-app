from frappe.desk.search import build_for_autosuggest, search_widget
import frappe
from custom_api.utils.response import send_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_bank_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        results = search_widget(
            "Bank",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=None,
            reference_doctype="Bank Account",
            ignore_user_permissions=0,
        )
        response = build_for_autosuggest(results, doctype="Bank")
        return send_response(
            status="success",
            message="Bank Accounts fetched successfully.",
            data={
                "data": response
            },
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Make Payment API Error")
        return send_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
            )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_company_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict({
            "company": company,
            "account_type": "Bank",
            "is_group":0
        })
        results = search_widget(
            "Account",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            reference_doctype="Bank Account",
            ignore_user_permissions=0,
        )
        response = build_for_autosuggest(results, doctype="Bank")
        return send_response(
            status="success",
            message="Company Accounts fetched successfully.",
            data={
                "data": response
            },
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Make Payment API Error")
        return send_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
            )