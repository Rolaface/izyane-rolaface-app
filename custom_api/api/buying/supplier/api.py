from custom_api.permission import require_permission
import frappe
from custom_api.utils.response import send_response, send_response_list
from .utils import validate_supplier_payload,  validate_supplier_update_payload
from ....utils.party_utils import parse_api_payload
from . import service

@frappe.whitelist(allow_guest=False, methods=["POST"])
@require_permission("Supplier", "create")
def create_supplier():
    try:
        data = parse_api_payload()
        validate_supplier_payload(data)
        
        supplier = service.create_supplier(data)
        frappe.db.commit()
        return send_response(status="success", message="Supplier created successfully.", data={"supplierId": supplier.name}, status_code=201, http_status=201)

    except frappe.exceptions.DuplicateEntryError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=409, http_status=409)
    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Supplier API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
@require_permission("Supplier", "write")
def update_supplier(id=None, **kwargs):
    try:        
        data = parse_api_payload()
        supplier_id = frappe.request.args.get("id")

        if not supplier_id:
            return send_response(status="fail", message="Supplier ID required as query parameter (?id=...)", status_code=400, http_status=400)
        if not frappe.db.exists("Supplier", supplier_id):
            return send_response(status="fail", message="Supplier not found", status_code=404, http_status=404)

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

        validate_supplier_update_payload(data)
        service.update_supplier(supplier_id, data)
        frappe.db.commit()
        return send_response(status="success", message="Supplier updated successfully", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Supplier API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Supplier", "read")
def get_supplier_by_id(id):
    try:
        if not frappe.db.exists("Supplier", id):
            return send_response(status="fail", message="Supplier not found", status_code=404, http_status=404)

        data = service.get_supplier_by_id(id)
        return send_response(status="success", message="Supplier retrieved successfully", status_code=200, data=data, http_status=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Supplier By ID Error")
        return send_response(status="error", message=f"Failed to retrieve supplier: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Supplier", "read")
def get_suppliers(page=1, page_size=20):
    try:
        try:
            page, page_size = int(page), int(page_size)
            if page < 1 or page_size < 1: raise ValueError
        except ValueError:
            return send_response(status="fail", message="Page constraints must be positive integers.", status_code=400, http_status=400)

        suppliers, total_suppliers, total_pages = service.get_suppliers(page, page_size)

        response_data = {
            "success": True, 
            "message": "Suppliers retrieved successfully", 
            "data": suppliers,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_suppliers,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }

        return send_response_list(status="success", message="Success", status_code=200, data=response_data, http_status=200)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Suppliers Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["DELETE"])
@require_permission("Supplier", "delete")
def delete_supplier(id=None):
    try:
        supplier_id = id or frappe.local.form_dict.get("id")
        if not supplier_id: 
            return send_response(status="fail", message="Supplier ID required", status_code=400, http_status=400)
        
        if not frappe.db.exists("Supplier", supplier_id): 
            return send_response(status="fail", message="Supplier not found", status_code=404, http_status=404)

        service.delete_supplier(supplier_id)
        frappe.db.commit()
        return send_response(status="success", message="Supplier deleted successfully", status_code=200, http_status=200)

    except frappe.exceptions.LinkExistsError:
        frappe.db.rollback()
        return send_response(status="fail", message="Cannot delete: Supplier is linked to existing transactions.", status_code=409, http_status=409)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Delete Supplier Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_supplier_status(id=None):
    try:
        data = parse_api_payload()
        supplier_id = frappe.request.args.get("id")
        raw_status = data.get("status")

        if not supplier_id:
            return send_response(status="fail", message="Supplier ID required", status_code=400, http_status=400)
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

        if not frappe.db.exists("Supplier", supplier_id):
            return send_response(status="fail", message="Supplier not found", status_code=404, http_status=404)

        final_status = service.update_supplier_status(supplier_id, status)
        frappe.db.commit()

        return send_response(status="success", message=f"Supplier status updated to {final_status}", status_code=200, http_status=200)

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Supplier Status API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)