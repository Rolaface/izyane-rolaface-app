from custom_api.helper import STATUS_MAP
from custom_api.utils.response import send_old_response
import frappe
from frappe.desk.doctype.bulk_update.bulk_update import _bulk_action
@frappe.whitelist(allow_guest=False, methods=["PATCH"] )
def update_purchase_order_status():
    data = frappe.request.get_json()
    poId = data["id"]
    status = data["status"]
    docnames = [poId]
    config = STATUS_MAP.get(status)
    if not poId:
        return send_old_response(
               status="fail",
               message="'id' parameter is required.",
               data=None,
               status_code=400,
               http_status=400,
               )
    if not config:
        return send_old_response(
            status="fail",
            message="'status' parameter is required.",
            data=None,
            status_code=400,
            http_status=400,
        )
    if not frappe.db.exists("Purchase Order", poId):
        return send_old_response(
            status="fail",
            message=f"Purchase Order '{poId}' not found.",
            data=None,
            status_code=404,
            http_status=404,
        )
    
    action = config["action"]
    if action:
        if isinstance(docnames, str):
            docnames = frappe.parse_json(docnames)

        response = _bulk_action("Purchase Order", docnames, action, data=None, task_id=None)
        if response:
            # Extract server messages from frappe message log
            server_messages = []
            for msg_str in frappe.local.message_log:
                msg = frappe.parse_json(msg_str)
                if "does not have doctype access via role permission for document" in msg.get("message", ""):
                    msg["message"] = f"You do not have permission to {status} the Purchase Order. Please contact your administrator."

                server_messages.append(msg.get("message", msg_str))

            return send_old_response(
                status="error",
                message=server_messages[0],
                status_code=422,
                http_status=422,
            )

        return send_old_response(
            status="success",
            message="Purchase Order status updated successfully",
            data={"poId": poId, "status": status},
            status_code=200,
            http_status=200,
        )
    else:
        frappe.db.sql(
            """
            UPDATE `tabPurchase Order`
            SET status = %s,
                modified = NOW(),
                modified_by = %s
            WHERE name = %s
            """,
            (status, frappe.session.user, poId),
        )

        frappe.db.commit()

        return send_old_response(
            status="success",
            message="Purchase Order status updated successfully",
            data={"poId": poId, "status": status},
            status_code=200,
            http_status=200,
        )
