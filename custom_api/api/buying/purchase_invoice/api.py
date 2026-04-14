from custom_api.utils.response import send_old_response, send_response_list
import frappe
from custom_api.api.buying.purchase_invoice.service import create_purchase_invoice_service, get_purchase_invoice_by_id, get_purchase_invoice_list

@frappe.whitelist(allow_guest = False, methods=["GET"])
def get():
    data = frappe.local.form_dict

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