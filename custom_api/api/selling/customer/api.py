import frappe
from custom_api.utils.response import send_response, send_response_list
from .utils import parse_api_payload, validate_customer_payload
from . import service

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_customer():
    try:
        data = parse_api_payload()
        validate_customer_payload(data)
        
        customer = service.create_customer(data)
        frappe.db.commit()
        return send_response(status="success", message="Customer created successfully.", data={"customerId": customer.name}, status_code=201, http_status=201)

    except frappe.exceptions.DuplicateEntryError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=409, http_status=409)
    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Customer API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_customer(id=None, **kwargs):
    try:        
        data = parse_api_payload()
        customer_id = frappe.request.args.get("id")

        if not customer_id:
            return send_response(status="fail", message="Customer ID required as query parameter (?id=...)", status_code=400, http_status=400)
        if not frappe.db.exists("Customer", customer_id):
            return send_response(status="fail", message="Customer not found", status_code=404, http_status=404)

        if data.get("status"):
            raw_status = data.get("status")
            status = str(raw_status).strip().lower()
            if status not in {"active", "inactive"}:
                return send_response(
                    status="fail", 
                    message=f"Invalid status '{raw_status}'. Allowed values are: 'active', 'inactive'.", 
                    status_code=400, 
                    http_status=400
                )

        validate_customer_payload(data)
        service.update_customer(customer_id, data)
        frappe.db.commit()
        return send_response(status="success", message="Customer updated successfully", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Customer API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customer_by_id(id):
    try:
        if not frappe.db.exists("Customer", id):
            return send_response(status="fail", message="Customer not found", status_code=404, http_status=404)

        data = service.get_customer_by_id(id)
        return send_response(status="success", message="Customer retrieved successfully", status_code=200, data=data, http_status=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Customer By ID Error")
        return send_response(status="error", message=f"Failed to retrieve customer: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customers(page=1, page_size=20):
    try:
        try:
            page, page_size = int(page), int(page_size)
            if page < 1 or page_size < 1: raise ValueError
        except ValueError:
            return send_response(status="fail", message="Page constraints must be positive integers.", status_code=400, http_status=400)

        customers, total_customers, total_pages = service.get_customers(page, page_size)

        response_data = {
            "success": True, 
            "message": "Customers retrieved successfully", 
            "data": customers,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_customers,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }

        return send_response_list(status="success", message="Success", status_code=200, data=response_data, http_status=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Customers Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_customer(id=None):
    try:
        customer_id = id or frappe.local.form_dict.get("id")
        if not customer_id: 
            return send_response(status="fail", message="Customer ID required", status_code=400, http_status=400)
        
        if not frappe.db.exists("Customer", customer_id): 
            return send_response(status="fail", message="Customer not found", status_code=404, http_status=404)

        service.delete_customer(customer_id)
        frappe.db.commit()
        return send_response(status="success", message="Customer deleted successfully", status_code=200, http_status=200)

    except frappe.exceptions.LinkExistsError:
        frappe.db.rollback()
        return send_response(status="fail", message="Cannot delete: Customer is linked to existing transactions.", status_code=409, http_status=409)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Delete Customer Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_customer_status(id=None):
    try:
        data = parse_api_payload()
        customer_id = frappe.request.args.get("id")
        raw_status = data.get("status")

        if not customer_id:
            return send_response(status="fail", message="Customer ID required", status_code=400, http_status=400)
        if not raw_status:
            return send_response(status="fail", message="Status is required", status_code=400, http_status=400)

        status = str(raw_status).strip().lower()
        valid_statuses = {"active", "inactive"}
        
        if status not in valid_statuses:
            return send_response(
                status="fail", 
                message=f"Invalid status '{raw_status}'. Allowed values are: 'active', 'inactive'.", 
                status_code=400, 
                http_status=400
            )

        if not frappe.db.exists("Customer", customer_id):
            return send_response(status="fail", message="Customer not found", status_code=404, http_status=404)

        final_status = service.update_customer_status(customer_id, status)
        frappe.db.commit()

        return send_response(status="success", message=f"Customer status updated to {final_status}", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Customer Status API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)