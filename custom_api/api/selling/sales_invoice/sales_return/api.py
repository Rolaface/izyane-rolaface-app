import frappe
from custom_api.config import zra_exception
from custom_api.permission import require_permission
from custom_api.utils.party_utils import parse_api_payload
from custom_api.utils.response import handle_api_error, send_response, send_response_list

from . import service
from .constant import ACTIONS
from .utils import ensure_return_document, normalize_payload, validate_payload


def get_request_id(value=None):
    return value or frappe.local.form_dict.get("id") or frappe.request.args.get("id")


def rollback():
    if getattr(frappe.local, "db", None):
        frappe.db.rollback()


@frappe.whitelist(allow_guest=False, methods=["POST"])
@require_permission("Sales Invoice", "create")
def create_sales_return():
    try:
        data = normalize_payload(parse_api_payload())
        validate_payload(data)
        invoice = service.create_sales_return(data)
        frappe.db.commit()
        doc_type = "Credit Note" if invoice.is_return else "Debit Note"
        return send_response(
            status="success",
            message=f"{doc_type} created successfully.",
            data={"id": invoice.name, "invoice_id": invoice.name, "doc_type": doc_type},
            status_code=201,
            http_status=201,
        )
    except Exception as exc:
        rollback()
        return handle_api_error(exc, "Create Sales Return API Error")


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
@require_permission("Sales Invoice", "write")
def update_sales_return(id=None):
    try:
        invoice_id = get_request_id(id)
        if not invoice_id:
            raise frappe.ValidationError("id is required.")
        data = normalize_payload(parse_api_payload())
        invoice = service.update_sales_return(invoice_id, data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Sales return updated successfully.",
            data={"id": invoice.name},
            status_code=200,
            http_status=200,
        )
    except Exception as exc:
        rollback()
        return handle_api_error(exc, "Update Sales Return API Error")


@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Sales Invoice", "read")
def get_sales_return_by_id(id=None):
    try:
        invoice_id = get_request_id(id)
        if not invoice_id:
            raise frappe.ValidationError("id is required.")
        invoice = ensure_return_document(frappe.get_doc("Sales Invoice", invoice_id))
        if not frappe.has_permission("Sales Invoice", "read", invoice):
            raise frappe.PermissionError("You do not have permission to read this sales return.")
        from custom_api.api.selling.sales_invoice import service as invoice_service

        data = invoice_service.get_sales_invoice_by_id(invoice.name, False)

        from frappe.utils import flt
        for inv_item, item_data in zip(invoice.items, data.get("items", [])):
            rate_val = flt(inv_item.rate) if inv_item.rate is not None else flt(inv_item.price_list_rate)
            item_data["rate"] = rate_val
            item_data["price_list_rate"] = flt(inv_item.price_list_rate) if inv_item.price_list_rate is not None else rate_val

        data.update({
            "doc_type": "Credit Note" if invoice.is_return else "Debit Note",
            "return_against": invoice.return_against,
            "docstatus": invoice.docstatus,
        })
        return send_response(
            status="success",
            message="Sales return retrieved successfully.",
            data=data,
            status_code=200,
            http_status=200,
        )
    except Exception as exc:
        return handle_api_error(exc, "Get Sales Return By ID Error")


@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Sales Invoice", "read")
def get_sales_returns(page=1, page_size=20):
    try:
        try:
            page, page_size = int(page), int(page_size)
        except (TypeError, ValueError) as exc:
            raise frappe.ValidationError("page and page_size must be integers.") from exc
        args = frappe.local.form_dict
        rows, total, total_pages = service.get_sales_returns(
            args, page, page_size, args.get("sort_by", "creation"), args.get("sort_order", "desc")
        )
        return send_response_list(
            status="success",
            message="Sales returns retrieved successfully.",
            data={
                "data": rows,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            },
            status_code=200,
            http_status=200,
        )
    except Exception as exc:
        return handle_api_error(exc, "Get All Sales Returns Error")


@frappe.whitelist(allow_guest=False, methods=["DELETE"])
@require_permission("Sales Invoice", "delete")
def delete_sales_return(id=None):
    try:
        invoice_id = get_request_id(id)
        if not invoice_id:
            raise frappe.ValidationError("id is required.")
        service.delete_sales_return(invoice_id)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Sales return deleted successfully.",
            status_code=200,
            http_status=200,
        )
    except Exception as exc:
        rollback()
        return handle_api_error(exc, "Delete Sales Return Error")


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
@require_permission("Sales Invoice", "write")
def update_sales_return_status(id=None, action=None):
    try:
        invoice_id = get_request_id(id)
        action = action or frappe.local.form_dict.get("action") or frappe.request.args.get("action")
        if not invoice_id or not action:
            raise frappe.ValidationError("id and action are required.")
        action = str(action).strip().lower()
        if action not in ACTIONS:
            raise frappe.ValidationError("action must be approved, cancelled, or amend.")

        invoice = ensure_return_document(frappe.get_doc("Sales Invoice", invoice_id))
        from custom_api.api.selling.sales_invoice import service as invoice_service

        result = invoice_service.update_sales_invoice_status(invoice.name, action)
        frappe.db.commit()
        label = {"approved": "approved", "cancelled": "cancelled", "amend": "amended"}[action]
        return send_response(
            status="success",
            message=f"Sales return {label} successfully.",
            data=result,
            status_code=200,
            http_status=200,
        )
    except (zra_exception.ZRAConnectionError, zra_exception.ZRAResponseError) as exc:
        rollback()
        return send_response(status="fail", message=str(exc), status_code=400, http_status=400)
    except Exception as exc:
        rollback()
        return handle_api_error(exc, "Update Sales Return Status API Error")
