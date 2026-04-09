from custom_api.api.taxes_and_charges.item.service import get_item_tax_templates_service, upsert_item_tax_template
import frappe
from custom_api.utils.response import send_old_response, send_response_list

@frappe.whitelist(methods=["POST"])
def create_or_update_tax_template():
    try:
        data = frappe.request.get_json()

        result = upsert_item_tax_template(data)

        return send_old_response(
            status="success",
            message="Item Tax Template saved successfully",
            data=result,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(message=str(e), title="Get Company API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["GET"])
def get():
    try:
        args = frappe.local.form_dict

        data = get_item_tax_templates_service(args)

        return send_response_list(
            status="success",
            message="Item Tax Templates retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(str(e), "Get Item Tax Templates API Error")

        return {
            "status": "fail",
            "message": str(e)
        }