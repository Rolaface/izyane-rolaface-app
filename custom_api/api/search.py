from erpnext.accounts.doctype.account.account import get_account_currency
from erpnext.accounts.doctype.bank_account.bank_account import get_default_company_bank_account, get_party_bank_account
from erpnext.accounts.party import get_party_account
from frappe.desk.search import build_for_autosuggest, search_widget
import frappe
from custom_api.utils.response import send_response
from erpnext.zra_client.generic_api import send_response as old_response

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
def parties_and_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        doc_filter = frappe.request.args.get("filter","")
        reference_doctype = frappe.request.args.get("reference_doctype", "Bank Account") # We have made Bank Account as default because API was initially develop for referebce doctye = Bank Account and because of so much update in the front-end we have make it default
        company = frappe.defaults.get_user_default("Company")
        filters = None

        if reference_doctype not in ["Bank Account", "Payment Entry"]:
            return send_response(
                status="fail",
                message="Invalid Reference Doctype.",
                status_code=400,
                http_status=400,
            )
        if doc_filter not in ["Company", "Supplier", "Bank", "Customer", "Currency", "Account", "Shareholder", "Employee"]:
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
                reference_doctype=reference_doctype,
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

# Below is the custome API of "payment_entry.payment_entry.get_party_details"
@frappe.whitelist(allow_guest=False, methods=["POST"])
def get_party_details(party_type, party, cost_center=None):
    company_default_bank_account = ""
    party_bank_account = ""
    company = frappe.defaults.get_user_default("Company")
    
    if not frappe.db.exists(party_type, party):
        return old_response(status="fail", message=f"Party {party} does not exist", data=None, status_code=400, http_status=400)

    party_account = get_party_account(party_type, party, company)
    account_currency = get_account_currency(party_account)
    _party_name = "title" if party_type == "Shareholder" else party_type.lower() + "_name"
    party_name = frappe.db.get_value(party_type, party, _party_name)
    if party_type in ["Customer", "Supplier"]:
        party_bank_account = get_party_bank_account(party_type, party)
        company_default_bank_account = get_default_company_bank_account(company, party_type, party)
        bank_account_ledger = frappe.get_cached_value("Bank Account", company_default_bank_account, ["account", "bank", "bank_account_no"], as_dict=1)
        bank_account_ledger["currency"] = frappe.db.get_value("Account", bank_account_ledger["account"], "account_currency") if bank_account_ledger["account"] else None

    return old_response(
            status="success",
            message="Bank Account created successfully.",
            data={
                    "party_ledger_account": party_account,
                    "party_name": party_name,
                    "party_account_currency": account_currency,
                    "party_bank_account": party_bank_account,
                    "company_bank_account": company_default_bank_account,
                    "company_account_ledger": bank_account_ledger
                },
            status_code=201,
            http_status=201,
        )