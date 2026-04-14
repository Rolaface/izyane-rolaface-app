from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
import frappe
from custom_api.utils.response import send_old_response, send_response_list
from .service import create_po_service, get_po_by_id, update_po_service, get_po_list

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create():
    try:
        data = frappe.local.form_dict
        create_po_service(data)

        return send_old_response(
            status="success",
            message="Purchase Order created successfully",
            status_code=201,
            http_status=201
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Purchase Order API Error")
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

@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update():
    try:
        data = frappe.local.form_dict
        po_id = frappe.request.args.get("id")

        if not po_id:
            frappe.throw("PO id is required")

        update_po_service(po_id, data)
        return send_old_response(
            status="success",
            message="Purchase Order updated successfully",
            status_code=201,
            http_status=201
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

@frappe.whitelist(allow_guest=False)
def get():
    data = frappe.local.form_dict

    page = int(data.get("page", 1))
    page_size = int(data.get("pageSize", 10))

    filters = {}

    if data.get("supplier"):
        filters["supplier"] = data.get("supplier")

    if data.get("status"):
        filters["status"] = data.get("status")
    
    search = data.get("search")

    response =  get_po_list(filters, page, page_size, search)
    return send_response_list(
        status="success",
        message="Purchase Orders retrieved successfully",
        data=response,
        status_code=200,
        http_status=200
    )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_by_id():
    try:
        po_id = frappe.request.args.get("id")

        if not po_id:
            return send_old_response(
                status="fail",
                message="Purchase Order ID is required",
                status_code=400,
                http_status=400
            )

        data = get_po_by_id(po_id)

        if not data:
            return send_old_response(
                status="fail",
                message="Purchase Order not found",
                status_code=404,
                http_status=404
            )

        return send_old_response(
            status="success",
            message="Purchase Order retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Purchase Order By ID API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_pi_from_po():

    po_id = frappe.request.args.get("po_id")
    if not po_id:
        frappe.throw("PO ID is required")

    try:
        pi_doc = make_purchase_invoice(po_id)

        pi_doc.docstatus = 0

        pi_doc.insert(ignore_permissions=True)

        return send_old_response(
            status="success",
            message="Purchase Invoice created successfully from Purchase Order",
            data=pi_doc,
            status_code=201,
            http_status=201
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create PI from PO Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )