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
            filter_fields='["swift_number"]',
            reference_doctype="Bank Account",
            ignore_user_permissions=0,
        )
        response = build_for_autosuggest(results, doctype="Bank")
        return send_response(
            status="success",
            message="Bank Accounts fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Make Payment API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_company_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict(
            {"company": company, "account_type": "Bank", "is_group": 0}
        )
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
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Make Payment API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_payable_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict(
            {"company": company, "account_type": "Payable", "is_group": 0}
        )
        results = search_widget(
            "Account",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            reference_doctype="Account",
            ignore_user_permissions=0,
        )
        response = build_for_autosuggest(results, doctype="Account")
        return send_response(
            status="success",
            message="Payable Accounts fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Payable Accounts API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_receivable_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict(
            {"company": company, "account_type": "Receivable", "is_group": 0}
        )
        results = search_widget(
            "Account",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            reference_doctype="Account",
            ignore_user_permissions=0,
        )
        response = build_for_autosuggest(results, doctype="Account")
        return send_response(
            status="success",
            message="Receivable Accounts fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Receivable Accounts API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_cost_centers():
    try:
        txt = frappe.request.args.get("search", "")
        company = frappe.defaults.get_user_default("Company")

        filters = frappe._dict({"company": company})

        results = search_widget(
            "Cost Center",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            reference_doctype="Cost Center",
            ignore_user_permissions=0,
        )

        response = build_for_autosuggest(results, doctype="Cost Center")

        return send_response(
            status="success",
            message="Cost Centers fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Cost Centers API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customers():
    try:
        txt = frappe.request.args.get("search", "")

        filters = frappe._dict({})

        results = search_widget(
            "Customer",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            reference_doctype="Customer",
            ignore_user_permissions=0,
        )

        response = build_for_autosuggest(results, doctype="Customer")

        return send_response(
            status="success",
            message="Customers fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Customers API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_suppliers():
    try:
        txt = frappe.request.args.get("search", "")

        filters = frappe._dict({})

        results = search_widget(
            "Supplier",
            txt.strip(),
            None,
            searchfield=None,
            page_length=10,
            filters=filters,
            reference_doctype="Supplier",
            ignore_user_permissions=0,
        )

        response = build_for_autosuggest(results, doctype="Supplier")

        return send_response(
            status="success",
            message="Suppliers fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Suppliers API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_bank_company_supplier_cutomer():
    try:
        txt = frappe.request.args.get("search", "")
        account_for = frappe.request.args.get("accountFor","")
        if account_for == "Company":
            response = frappe.defaults.get_user_default("Company")
        else:
            filter_fields = None
            if account_for == "Supplier":
                filter_fields = '["default_currency"]'
            response = search_widget(
                account_for,
                txt.strip(),
                None,
                searchfield=None,
                page_length=10,
                filters=None,
                filter_fields=filter_fields,
                reference_doctype="Bank Account",
                ignore_user_permissions=0,
                as_dict= True,

            )
        
        return send_response(
            status="success",
            message="Suppliers fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Suppliers API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )