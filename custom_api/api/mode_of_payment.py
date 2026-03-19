from erpnext.zra_client.generic_api import send_response
import frappe

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create():
    data = frappe.request.get_json()

    name         = data.get("name")
    payment_type = data.get("type")
    enabled      = data.get("enabled", 1)
    default_account = data.get("default_account")

    if not name:
        return send_response(status="fail", message="'name' is required.", data=None, status_code=400, http_status=400)

    if not payment_type:
        return send_response(status="fail", message="'type' is required. Allowed: Bank, Cash, General", data=None, status_code=400, http_status=400)

    if payment_type not in ("Bank", "Cash", "General", "Phone"):
        return send_response(status="fail", message=f"Invalid type '{payment_type}'. Allowed: Bank, Cash, General", data=None, status_code=400, http_status=400)

    if frappe.db.exists("Mode of Payment", name):
        return send_response(status="fail", message=f"Mode of Payment '{name}' already exists.", data=None, status_code=409, http_status=409)

    if not default_account:
        return send_response(status="fail", message="At least one account is required.", data=None, status_code=400, http_status=400)
    
    if not frappe.db.exists("Account", default_account):
        return send_response(status="fail", message=f"Account '{default_account}' does not exist.", data=None, status_code=404, http_status=404)

    company = frappe.defaults.get_user_default("Company")

    try:

        mop_doc = frappe.get_doc({
            "doctype": "Mode of Payment",
            "mode_of_payment": name,
            "type": payment_type,
            "enabled": enabled,
            "accounts": [{
                            "company": company,
                            "default_account": default_account,
                        }]
        })

        mop_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Mode of Payment created successfully.",
            data={"modeOfPaymentId": mop_doc.name},
            status_code=201,
            http_status=201,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Mode Of Payment Fail")
        return send_response(
            status="fail", message="Something went wrong, Please try again later", data=None, status_code=500, http_status=500
        )