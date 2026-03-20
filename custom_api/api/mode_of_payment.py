from erpnext.zra_client.generic_api import send_response
import frappe
from frappe.utils import ceil
from frappe.desk.search import build_for_autosuggest, search_widget

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

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get():
    company      = frappe.request.args.get("company") or frappe.defaults.get_user_default("Company")
    payment_type = frappe.request.args.get("type")
    enabled      = frappe.request.args.get("enabled")
    name         = frappe.request.args.get("name")
    search       = frappe.request.args.get("search")
    page         = int(frappe.request.args.get("page", 1))
    page_size    = int(frappe.request.args.get("page_size", 10))

    filters = []
    if payment_type:
        filters.append(["type", "=", payment_type])
    if enabled is not None:
        filters.append(["enabled", "=", int(enabled)])
    if name:
        filters.append(["name", "=", name])
    if search:
        filters.append(["mode_of_payment", "like", f"%{search}%"])

    total = frappe.db.count("Mode of Payment", filters=filters)
    mop_list = frappe.db.get_all(
        "Mode of Payment",
        filters=filters,
        fields=["name", "mode_of_payment as modeOfPayment", "type", "enabled"],
        order_by="creation desc",
        limit=page_size,
        limit_start=(page - 1) * page_size,
    )

    for mop in mop_list:
        account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mop["name"], "company": company},
            ["default_account"],
            as_dict=True
        )
        mop["defaultAccount"] = account.get("default_account") if account else None

    return send_response(
        status="success",
        message="Mode of Payments fetched successfully.",
        data={
            "modeOfPayments": mop_list,
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
def update():
    data = frappe.request.get_json()

    name            = data.get("name")
    payment_type    = data.get("type")
    enabled         = data.get("enabled")
    default_account = data.get("default_account")
    company         = frappe.defaults.get_user_default("Company")

    if not name:
        return send_response(status="fail", message="'name' is required.", data=None, status_code=400, http_status=400)

    if not frappe.db.exists("Mode of Payment", name):
        return send_response(status="fail", message=f"Mode of Payment '{name}' not found.", data=None, status_code=404, http_status=404)

    if payment_type and payment_type not in ("Bank", "Cash", "General"):
        return send_response(status="fail", message="Invalid 'type'. Allowed: Bank, Cash, General", data=None, status_code=400, http_status=400)

    if default_account and not frappe.db.exists("Account", default_account):
        return send_response(status="fail", message=f"Account '{default_account}' does not exist.", data=None, status_code=404, http_status=404)

    if not any([payment_type, enabled is not None, default_account]):
        return send_response(status="fail", message="Nothing to update. Provide 'type', 'enabled' or 'default_account'.", data=None, status_code=400, http_status=400)

    mop_updates = {}
    if payment_type:
        mop_updates["type"] = payment_type
    if enabled is not None:
        mop_updates["enabled"] = int(enabled)

    if mop_updates:
        frappe.db.set_value("Mode of Payment", name, mop_updates)

    if default_account:
        existing = frappe.db.exists(
            "Mode of Payment Account",
            {"parent": name, "company": company}
        )
        if existing:
            frappe.db.set_value("Mode of Payment Account", existing, "default_account", default_account)
        else:
            # No account for this company yet — create one
            mop_doc = frappe.get_doc("Mode of Payment", name)
            mop_doc.append("accounts", {
                "company": company,
                "default_account": default_account,
            })
            mop_doc.save(ignore_permissions=True)

    frappe.db.commit()

    return send_response(
        status="success",
        message="Mode of Payment updated successfully.",
        data={"name": name},
        status_code=200,
        http_status=200,
    )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_default_accounts():
    
    company = frappe.defaults.get_user_default("Company")
    txt = frappe.request.args.get("search", "")

    results = search_widget(
                "Account",
                txt.strip(),
                page_length=10,
                filters=[
                        ["Account","account_type","in","Bank, Cash, Receivable"],
                        ["Account","is_group","=",0],
                        ["Account","company","=",f"{company}"]
                        ],
                reference_doctype="Mode of Payment Account",
	        )
    response =  build_for_autosuggest(results, doctype="Account")
    return send_response(
        status="success",
        message="Mode of Payment updated successfully.",
        data=response,
        status_code=200,
        http_status=200,
    )