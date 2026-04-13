import frappe
from custom_api.utils.response import send_response, send_response_list
from .utils import validate_sales_invoice_payload
from ....utils.party_utils import parse_api_payload
from . import service

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_sales_invoice():
    try:
        data = parse_api_payload()
        validate_sales_invoice_payload(data)
        
        invoice = service.create_sales_invoice(data)
        frappe.db.commit()
        return send_response(status="success", message="Sales Invoice created successfully.", data={"invoiceId": invoice.name}, status_code=201, http_status=201)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Sales Invoice API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_sales_invoice(id=None, **kwargs):
    try:        
        data = parse_api_payload()
        invoice_id = id or frappe.request.args.get("id")

        if not invoice_id:
            return send_response(status="fail", message="Invoice ID required as query parameter (?id=...)", status_code=400, http_status=400)
        if not frappe.db.exists("Sales Invoice", invoice_id):
            return send_response(status="fail", message="Sales Invoice not found", status_code=404, http_status=404)

        validate_sales_invoice_payload(data, is_update=True)
        service.update_sales_invoice(invoice_id, data)
        frappe.db.commit()
        return send_response(status="success", message="Sales Invoice updated successfully", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Sales Invoice API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_sales_invoice_by_id(id):
    try:
        if not frappe.db.exists("Sales Invoice", id):
            return send_response(status="fail", message="Sales Invoice not found", status_code=404, http_status=404)

        data = service.get_sales_invoice_by_id(id)
        return send_response(status="success", message="Sales Invoice retrieved successfully", status_code=200, data=data, http_status=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Sales Invoice By ID Error")
        return send_response(status="error", message=f"Failed to retrieve invoice: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_sales_invoices(page=1, page_size=20):
    try:
        try:
            page, page_size = int(page), int(page_size)
            if page < 1 or page_size < 1: raise ValueError
        except ValueError:
            return send_response(status="fail", message="Page constraints must be positive integers.", status_code=400, http_status=400)

        invoices, total_invoices, total_pages = service.get_sales_invoices(page, page_size)

        response_data = {
            "success": True, 
            "message": "Sales Invoices retrieved successfully", 
            "data": invoices,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_invoices,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }

        return send_response_list(status="success", message="Success", status_code=200, data=response_data, http_status=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Sales Invoices Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_sales_invoice(id=None):
    try:
        invoice_id = id or frappe.local.form_dict.get("id")
        if not invoice_id: 
            return send_response(status="fail", message="Invoice ID required", status_code=400, http_status=400)
        
        if not frappe.db.exists("Sales Invoice", invoice_id): 
            return send_response(status="fail", message="Sales Invoice not found", status_code=404, http_status=404)

        service.delete_sales_invoice(invoice_id)
        frappe.db.commit()
        return send_response(status="success", message="Sales Invoice deleted successfully", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Delete Sales Invoice Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_sales_invoice_status(id=None):
    try:
        data = parse_api_payload()
        invoice_id = id or frappe.request.args.get("id")
        raw_action = data.get("action")

        if not invoice_id:
            return send_response(status="fail", message="Invoice ID required", status_code=400, http_status=400)
        if not raw_action:
            return send_response(status="fail", message="Action is required (submit or cancel)", status_code=400, http_status=400)

        action = str(raw_action).strip().lower()
        if action not in {"submit", "cancel"}:
            return send_response(
                status="fail", 
                message=f"Invalid action '{raw_action}'. Allowed values are: 'submit', 'cancel'.", 
                status_code=400, 
                http_status=400
            )

        if not frappe.db.exists("Sales Invoice", invoice_id):
            return send_response(status="fail", message="Sales Invoice not found", status_code=404, http_status=404)

        final_status = service.update_sales_invoice_status(invoice_id, action)
        frappe.db.commit()

        return send_response(status="success", message=f"Sales Invoice {action}ted successfully. Status is now {final_status}", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Sales Invoice Status API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)