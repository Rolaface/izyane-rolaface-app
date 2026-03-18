import frappe
from custom_api.utils.response import send_response

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create():
    data = frappe.request.get_json()

    bank = data.get("bankName")
    account_number = data.get("accountNo")
    branch_address = data.get("branchAddress")
    currency = data.get("currency", "")
    branch_code = data.get("sortCode", "")
    iban = data.get("iban", "")
    account_holder_name = data.get("accountHolderName","")
    last_integration_date = data.get("dateAdded", None)
    accountFor = data.get("accountFor")
    reporting_account = data.get("reportingAccount")
    party = data.get("partyName")
    is_company_account = 1 if accountFor == "Company" else 0
    company =  frappe.defaults.get_user_default("Company") if accountFor == "Compnay" else None

    if not accountFor:
        return send_response(status="fail", message=" is required.", data=None, status_code=400, http_status=400)

    if not bank:
        return send_response(status="fail", message="'bank' is required.", data=None, status_code=400, http_status=400)
    if not account_number:
        return send_response(status="fail", message="'account_number' is required.", data=None, status_code=400, http_status=400)

    if not frappe.db.exists("Bank", bank):
        return send_response(status="fail", message=f"Bank '{bank}' does not exist.", data=None, status_code=404, http_status=404)

    if frappe.db.exists("Bank Account", {"bank_account_no": account_number}):
        return send_response(status="fail", message=f"Bank Account with number '{account_number}' already exists.", data=None, status_code=409, http_status=409)

    if accountFor != "Company" and party == None:
        return send_response(status="fail", message="Party Name is required.", data=None, status_code=400, http_status=400)
    try:
        if accountFor == "Company":
            ledger_account = frappe.get_doc({
                                "doctype":"Account",
                                "disabled": 0,
                                "is_group": 0,
                                "company": company,
                                "root_type": "Asset",
                                "report_type": "Balance Sheet",
                                "account_currency": currency,
                                "account_type": "Bank",
                                "freeze_account": "No",
                                "account_name": bank+ " " +currency,
                                "parent_account": reporting_account
                            })
            ledger_account.insert(ignore_permissions=True)
            frappe.db.commit()

        bank_account = frappe.get_doc({
            "doctype": "Bank Account",
            "account_name": account_holder_name,
            "bank": bank,
            "bank_account_no": account_number,
            "company": company,
            "currency": currency,
            "branch_code": branch_code,
            "iban": iban,
            "is_company_account": is_company_account,
            "branch_address": branch_address,
            "last_integration_date": last_integration_date,
            "account": ledger_account.name,
            "party_type": accountFor if accountFor != "Company" else None,
            "party": party
        })

        bank_account.insert(ignore_permissions=True)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Bank Account created successfully.",
            data={"bank_account_id": bank_account.name},
            status_code=201,
            http_status=201,
        )
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Bank Acount Fail")
        return send_response(
            status="fail", message="Something went wrong, Please try again later", data=None, status_code=500, http_status=500
        )