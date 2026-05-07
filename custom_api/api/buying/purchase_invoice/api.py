from custom_api.permission import require_permission
from custom_api.utils.response import send_old_response, send_response_list
import frappe
from custom_api.api.buying.purchase_invoice.service import create_purchase_invoice_service, get_purchase_invoice_by_id, get_purchase_invoice_list, update_pi_service

@frappe.whitelist(allow_guest = False, methods=["GET"])
@require_permission("Purchase Invoice", "read")
def get():
    data = frappe.request.args

    try:
        response =  get_purchase_invoice_list(
                                        filters=data,
                                        page=int(data.get("page", 1)),
                                        page_size=int(data.get("page_size", 10)),
                                        search=data.get("search", "")
                                    )
        return send_response_list(
            status="success",
            message="Purchase Invoices retrieved successfully",
            data=response,
            status_code=200,
            http_status=200
        )
    except Exception as e:
        frappe.log_error(str(e), "Get Purchase Invoices API Error")

        return send_response_list(
            status="fail",
            message=str(e),
            data=[],
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest = False, methods=["POST"])
@require_permission("Purchase Invoice", "create")
def create():
    data = frappe.local.form_dict
    try:
        create_purchase_invoice_service(data)

        return send_old_response(
                    status="success",
                    message="Purchase Invoice created successfully",
                    status_code=201,
                    http_status=201
                )
    except Exception as e:
        frappe.log_error(str(e), "Create Purchase Invoice API Error")

        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Purchase Invoice", "read")
def get_by_id():
    try:
        pi_id = frappe.request.args.get("id")

        if not pi_id:
            return send_old_response(
                status="fail",
                message="Purchase Invoice ID is required",
                status_code=400,
                http_status=400
            )

        data = get_purchase_invoice_by_id(pi_id)

        if not data:
            return send_old_response(
                status="fail",
                message="Purchase Invoice not found",
                status_code=404,
                http_status=404
            )

        return send_old_response(
            status="success",
            message="Purchase Invoice retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Purchase Invoice By ID API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["PUT"])
@require_permission("Purchase Invoice", "write")
def update():
    try:
        data = frappe.local.form_dict
        pi_id = frappe.request.args.get("id")

        if not pi_id:
            frappe.throw("PI is required")

        update_pi_service(pi_id, data)
        return send_old_response(
            status="success",
            message="Purchase Invoice updated successfully",
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Purchase Order API Error")
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["PATCH"])
def update_status():
    temp_status = None
    try:
        data = frappe.request.get_json()
        pId = data.get("id")
        new_status = data.get("status")
        if not pId:
            return send_old_response(status="fail", message="'id' is required.", data=None, status_code=400, http_status=400)

        if not new_status:
            return send_old_response(status="fail", message="'status' is required.", data=None, status_code=400, http_status=400)

        if not frappe.db.exists("Purchase Invoice", pId):
            return send_old_response(status="fail", message=f"Purchase Invoice '{pId}' not found.", data=None, status_code=404, http_status=404)

        pi_doc = frappe.get_doc("Purchase Invoice", pId)

        valid_statuses = ["Return","Submitted","Paid","Party Paid",
                          "Cancelled","Internal Transfer","Debit Note Issued"]

        if new_status not in valid_statuses:
            return send_old_response(
                status="fail",
                message=f"'status' must be one of: {', '.join(valid_statuses)}.",
                data=None,
                status_code=400,
                http_status=400
            )

        if new_status == "Submitted":
            if pi_doc.docstatus != 0:
                return send_old_response(status="fail", message="Only Draft invoices can be submitted.", data=None, status_code=400, http_status=400)
            temp_status = "Submit"
            pi_doc.submit()
        elif new_status == "Cancelled":
            if pi_doc.docstatus != 1:
                return send_old_response(status="fail", message="Only Submitted invoices can be cancelled.", data=None, status_code=400, http_status=400)
            temp_status = "Cancel"
            pi_doc.cancel()
        else:
            frappe.db.sql("""
                    UPDATE `tabPurchase Invoice`
                    SET status = %s,
                        modified = NOW(),
                        modified_by = %s
                    WHERE name = %s
                """, (new_status, frappe.session.user, pId))

        frappe.db.commit()

        updated_status = frappe.db.get_value("Purchase Invoice", pId, "status")

        return send_old_response(
            status="success",
            message="Purchase Invoice status updated successfully.",
            data={"id": pId, "status": updated_status},
            status_code=200,
            http_status=200
        )

    except frappe.exceptions.PermissionError:
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        return send_old_response(
            status="fail",
            message=f"You do not have permission to {temp_status} the status of this Purchase Invoice.Please contact your Administrator.",
            data=None,
            status_code=403,
            http_status=403
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Purchase Invoice Status Error")
        return send_old_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )