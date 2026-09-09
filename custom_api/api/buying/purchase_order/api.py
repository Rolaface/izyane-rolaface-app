from custom_api.api.selling.sales_invoice.utils import validate_receivable_account_for_currency
from custom_api.permission import require_permission
from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
import frappe
from custom_api.utils.response import send_old_response, send_response_list
from .service import create_po_service, get_po_by_id, update_po_service, get_po_list

@frappe.whitelist(allow_guest=False, methods=["POST"])
@require_permission("Purchase Order", "create")
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
@require_permission("Purchase Order", "write")
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

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Purchase Order", "read")
def get():
    data = frappe.request.args
    page = int(data.get("page", 1))
    page_size = int(data.get("pageSize", 10))

    filters = {}
    order_by = data.get("order_by", "creation desc")
    if data.get("supplier"):
        filters["supplier"] = data.get("supplier")

    statuses = data.get("status")
    if statuses:
        statuses = statuses.split(",")
        mapped_statuses = []

        for status in statuses:
            if status == "Approved":
                mapped_statuses.extend(["To Receive", "To Receive and Bill"])
            else:
                mapped_statuses.append(status)

        filters["status"] = ["in", list(set(mapped_statuses))]

    
    search = data.get("search")

    response =  get_po_list(filters, page, page_size, search, order_by)
    return send_response_list(
        status="success",
        message="Purchase Orders retrieved successfully",
        data=response,
        status_code=200,
        http_status=200
    )

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Purchase Order", "read")
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
@require_permission("Purchase Invoice", "create")
def create_pi_from_po():

    po_id = frappe.request.args.get("po_id")
    if not po_id:
        frappe.throw("PO ID is required")

    try:
        default_payment_mode = None
        company_name = frappe.defaults.get_user_default("Company")
        company_doc = frappe.get_doc("Company", company_name)
        if company_doc.custom_extended_details:
            extended_details = company_doc.custom_extended_details[0]
            if extended_details.default_payment_mode:
                default_payment_mode = extended_details.default_payment_mode

        pi_doc = make_purchase_invoice(po_id)
        currency = pi_doc.currency
        account = validate_receivable_account_for_currency(currency, "Payable", "Liability")
        pi_doc.credit_to = account
        pi_doc.docstatus = 0
        pi_doc.allocate_advances_automatically = 1
        pi_doc.only_include_allocated_payments = 1
        pi_doc.update_stock = 1
        supplier = pi_doc.supplier
        terms_and_condition = frappe.get_value("Terms and Conditions", f"{supplier} Buying Terms", ["name", "terms"])
        pi_doc.tc_name = terms_and_condition[0] if terms_and_condition else None
        pi_doc.terms = terms_and_condition[1] if terms_and_condition else None
        pi_doc.append("custom_invoice_metadata", {"payment_mode": default_payment_mode})
        pi_doc.insert(ignore_permissions=True)

        return send_old_response(
            status="success",
            message="Purchase Invoice created successfully from Purchase Order",
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