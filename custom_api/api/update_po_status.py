import frappe
from frappe.desk.doctype.bulk_update.bulk_update import _bulk_action
from custom_api.utils.response import send_response

@frappe.whitelist(allow_guest=False, methods=["PATCH"] )
def update_purchase_order_status():
    data = frappe.request.get_json()
    poId = data["id"]
    status = data["status"]
    docnames = [poId]
    if not poId:
        return send_response(
               status="fail",
               message="'id' parameter is required.",
               data=None,
               status_code=400,
               http_status=400,
               )
    if not status:
        return send_response(
            status="fail",
            message="'status' parameter is required.",
            data=None,
            status_code=400,
            http_status=400,
        )
    if not frappe.db.exists("Purchase Order", poId):
        return send_response(
            status="fail",
            message=f"Purchase Order '{poId}' not found.",
            data=None,
            status_code=404,
            http_status=404,
        )

    if status not in ["Completed"]:
        if isinstance(docnames, str):
            docnames = frappe.parse_json(docnames)
        if status =="Approved":
            status = "submit"
        if status == "Cancelled":
            status = "cancel"

        response = _bulk_action("Purchase Order", docnames, status, data=None, task_id=None)
        return send_response(
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

        return send_response(
            status="success",
            message="Purchase Order status updated successfully",
            data={"poId": poId, "status": status},
            status_code=200,
            http_status=200,
        )
