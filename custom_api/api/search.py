from frappe.desk.search import build_for_autosuggest, search_widget
import frappe
from custom_api.utils.response import send_response

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
        doc_filter = frappe.request.args.get("filter","")
        company = frappe.defaults.get_user_default("Company")
        filters = None

        if doc_filter not in ["Company", "Supplier", "Bank", "Customer", "Currency", "Account"]:
            return send_response(
                status="fail",
                message="Invalid Filter.",
                status_code=400,
                http_status=400,
            )

        if doc_filter == "Company":
            currency = frappe.db.get_value("Company", company, "default_currency")
            response = {"company": company, "currency":currency}
        else:
            filter_fields = None
            if doc_filter in ["Supplier", "Customer"]:
                filter_fields = '["default_currency"]'
            if doc_filter == "Bank":
                filter_fields = '["swift_number"]'

            if doc_filter == "Account":
                filters = frappe._dict({"account_type": "Bank", "company": company, "is_group":0})

            response = search_widget(
                doc_filter,
                txt.strip(),
                None,
                searchfield=None,
                page_length=10,
                filters=filters,
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