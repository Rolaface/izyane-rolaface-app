from custom_api.api.item.service import create_item_service, get_items_service, update_item_service
from custom_api.utils.response import send_old_response
import frappe
from frappe import _

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create():
    try:
        data = frappe.request.get_json()

        item = create_item_service(data)

        return send_old_response(
            status="success",
            message="Item created successfully",
            data=item.name,
            status_code=200,
            http_status=200
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Item API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get():
    try:
        params = frappe.request.args

        data = get_items_service(params)

        return send_old_response(
            status="success",
            message="Items retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Items API Error")
        return send_old_response(
                    status="fail",
                    message=str(e),
                    status_code=500,
                    http_status=500
                )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_by_id():
    try:
        params = frappe.request.args

        data = get_items_service(params)

        return send_old_response(
            status="success",
            message="Items retrieved successfully",
            data=data["data"][0] if data.get("data") else None,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Items API Error")
        return send_old_response(
                    status="fail",
                    message=str(e),
                    status_code=500,
                    http_status=500
                )

@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update():
    try:
        id = frappe.request.args.get("item_code")
        data = frappe.request.get_json()

        item = update_item_service(id, data)

        return {
            "status": "success",
            "message": "Item updated successfully",
            "data": item.name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Item API Error")
        frappe.throw(str(e))