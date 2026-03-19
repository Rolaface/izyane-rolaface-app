import frappe
from custom_api.utils.response import send_response
from erpnext.zra_client.generic_api import send_response as old_response
from frappe.utils import ceil

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
    isDefault = data.get("isDefault", 0)
    isDisabled = data.get("isDisabled",0)

    is_company_account = 1 if accountFor == "Company" else 0
    company =  frappe.defaults.get_user_default("Company") if accountFor == "Company" else None
    if not accountFor:
        return old_response(status="fail", message=" is required.", data=None, status_code=400, http_status=400)

    if not bank:
        return old_response(status="fail", message="'bank' is required.", data=None, status_code=400, http_status=400)
    if not account_number:
        return old_response(status="fail", message="'account_number' is required.", data=None, status_code=400, http_status=400)

    if not frappe.db.exists("Bank", bank):
        return old_response(status="fail", message=f"Bank '{bank}' does not exist.", data=None, status_code=404, http_status=404)

    if frappe.db.exists("Bank Account", {"bank_account_no": account_number}):
        return old_response(status="fail", message=f"Bank Account with number '{account_number}' already exists.", data=None, status_code=409, http_status=409)

    if accountFor != "Company" and party == None:
        return old_response(status="fail", message="Party Name is required.", data=None, status_code=400, http_status=400)
    
    if reporting_account and frappe.db.exists("Bank Account", {"account": reporting_account}):
        
        return old_response(status="fail", message=f" {reporting_account} reporting account is already use another account.", 
                            data=None, status_code=400, http_status=400)
    try:
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
            "account": reporting_account,
            "party_type": accountFor if accountFor != "Company" else None,
            "party": party if accountFor != "Company" else None,
            "is_default": isDefault,
            "disabled": isDisabled,
            "bank_account_currency": currency
        })

        bank_account.insert(ignore_permissions=True)
        frappe.db.commit()

        return old_response(
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
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get():
    company    = frappe.request.args.get("company", None)
    party_type = frappe.request.args.get("party_type")
    party      = frappe.request.args.get("party")
    bank       = frappe.request.args.get("bank")
    disabled   = frappe.request.args.get("disabled")
    page       = int(frappe.request.args.get("page", 1))
    page_size  = int(frappe.request.args.get("page_size", 10))
    
    filters = {}
    if company:
        filters = {"company": frappe.defaults.get_user_default("Company"), "is_company_account":1}
    if party_type:
        filters["party_type"] = party_type
    if party:
        filters["party"] = party
    if bank:
        filters["bank"] = bank
    if disabled is not None:
        filters["disabled"] = int(disabled)

    fields = [
        "name", "account_name as accountHolderName", "bank as bankName", "bank_account_no as accountNo",
        "branch_code as sortCode", "branch_address as branchAddress", "iban",
        "is_company_account", "is_default as isDefault", "disabled as isDisabled",
        "party_type as accountFor", "party as partyName", "company",
        "last_integration_date as dateAdded", "account as ledgerAccount"
    ]

    total = frappe.db.count("Bank Account", filters=filters)
    bank_accounts = frappe.db.get_all(
        "Bank Account",
        filters=filters,
        fields=fields,
        order_by="creation desc",
        limit=page_size,
        limit_start=(page - 1) * page_size,
    )

    # For company accounts, fetch currency from tabAccount via the linked account field
    account_names = [
        ba.get("ledgerAccount") for ba in bank_accounts
        if ba.get("is_company_account") and ba.get("ledgerAccount")
    ]

    currency_map = {}
    if account_names:
        account_records = frappe.db.get_all(
            "Account",
            filters={"name": ["in", account_names]},
            fields=["name", "account_currency as currency"]
        )
        currency_map = {a["name"]: a["currency"] for a in account_records}

    for ba in bank_accounts:
        if ba.get("is_company_account"):
            ba["currency"] = currency_map.get(ba.get("ledgerAccount"))
        else:
            ba["currency"] = None

    return send_response(
        status="success",
        message="Bank Accounts fetched successfully.",
        data={
            "bank_accounts": bank_accounts,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": ceil(total / page_size),
                "has_next": page * page_size < total,
                "has_prev": page > 1,
            }
        },
        status_code=200,
        http_status=200,
    )

@frappe.whitelist(allow_guest=False, methods=["PUT"])
def set_bank_account_status():
    data = frappe.request.get_json()

    bank_account_id = data.get("bankAccountId")
    is_default      = data.get("isDefault")
    is_disabled     = data.get("isDisabled")

    if not bank_account_id:
        return send_response(status="fail", message="'bankAccountId' is required.", data=None, status_code=400, http_status=400)

    if not frappe.db.exists("Bank Account", bank_account_id):
        return send_response(status="fail", message=f"Bank Account '{bank_account_id}' not found.", data=None, status_code=404, http_status=404)

    updates = {}
    if is_default is not None:
        updates["is_default"] = int(is_default)
    if is_disabled is not None:
        updates["disabled"] = int(is_disabled)

    if not updates:
        return send_response(status="fail", message="Nothing to update. Provide 'isDefault' or 'isDisabled'.", data=None, status_code=400, http_status=400)

    frappe.db.set_value("Bank Account", bank_account_id, updates)
    frappe.db.commit()

    return old_response(
        status="success",
        message="Bank Account updated successfully.",
        status_code=200,
        http_status=200,
    )