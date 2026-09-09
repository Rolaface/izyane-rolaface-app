from custom_api.permission import require_permission
import frappe
from custom_api.utils.response import send_response, send_response_list
from .utils import validate_sales_invoice_payload
from ....utils.party_utils import parse_api_payload
from . import service
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return
from custom_api.config import zra_exception

@frappe.whitelist(allow_guest=False, methods=["POST"])
@require_permission("Sales Invoice", "create")
def create_sales_invoice():
    try:
        data = parse_api_payload()
        validate_sales_invoice_payload(data)

        invoice = service.create_sales_invoice(data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Sales Invoice created successfully.",
            data={"invoiceId": invoice.name},
            status_code=201,
            http_status=201,
        )

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Sales Invoice API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
@require_permission("Sales Invoice", "write")
def update_sales_invoice(id=None, **kwargs):
    try:
        data = parse_api_payload()
        invoice_id = id or frappe.request.args.get("id")

        if not invoice_id:
            return send_response(
                status="fail",
                message="Invoice ID required as query parameter (?id=...)",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Sales Invoice", invoice_id):
            return send_response(
                status="fail",
                message="Sales Invoice not found",
                status_code=404,
                http_status=404,
            )

        validate_sales_invoice_payload(data, is_update=True)
        service.update_sales_invoice(invoice_id, data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Sales Invoice updated successfully",
            status_code=200,
            http_status=200,
        )

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Update Sales Invoice API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Sales Invoice", "read")
def get_sales_invoice_by_id(id, is_credit_note=False, is_sales_debit_note=False):
    try:
        if not frappe.db.exists("Sales Invoice", id):
            return send_response(
                status="fail",
                message="Sales Invoice not found",
                status_code=404,
                http_status=404,
            )

        data = service.get_sales_invoice_by_id(id, is_credit_note, is_sales_debit_note)
        return send_response(
            status="success",
            message="Sales Invoice retrieved successfully",
            status_code=200,
            data=data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Sales Invoice By ID Error")
        return send_response(
            status="error",
            message=f"Failed to retrieve invoice: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
# @require_permission("Sales Invoice", "read")
def get_sales_invoices(page=1, page_size=20):
    data = frappe.local.form_dict
    search = data.get("search")
    try:
        try:
            page, page_size = int(page), int(page_size)
            if page < 1 or page_size < 1:
                raise ValueError
        except ValueError:
            return send_response(
                status="fail",
                message="Page constraints must be positive integers.",
                status_code=400,
                http_status=400,
            )

        invoices, total_invoices, total_pages = service.get_sales_invoices(
            data,page, page_size,search
        )

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
                "has_prev": page > 1,
            },
        }

        return send_response_list(
            status="success",
            message="Success",
            status_code=200,
            data=response_data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Sales Invoices Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["DELETE"])
@require_permission("Sales Invoice", "delete")
def delete_sales_invoice(id=None):
    try:
        invoice_id = id or frappe.local.form_dict.get("id")
        if not invoice_id:
            return send_response(
                status="fail",
                message="Invoice ID required",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Sales Invoice", invoice_id):
            return send_response(
                status="fail",
                message="Sales Invoice not found",
                status_code=404,
                http_status=404,
            )

        service.delete_sales_invoice(invoice_id)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Sales Invoice deleted successfully",
            status_code=200,
            http_status=200,
        )

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Delete Sales Invoice Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_sales_invoice_status(id=None, action=None):
    try:
        invoice_id = id or frappe.request.args.get("id")
        raw_action = action or frappe.request.args.get("action")

        if not invoice_id:
            return send_response(
                status="fail",
                message="Invoice ID is required",
                status_code=400,
                http_status=400,
            )

        if not raw_action:
            return send_response(
                status="fail",
                message="Action is required (approved, cancelled, amend)",
                status_code=400,
                http_status=400,
            )

        action = str(raw_action).strip().lower()

        if action not in {"approved", "cancelled", "amend"}:
            return send_response(
                status="fail",
                message=f"Invalid action '{raw_action}'. Allowed values: approved, cancelled, amend",
                status_code=400,
                http_status=400,
            )

        if not frappe.db.exists("Sales Invoice", invoice_id):
            return send_response(
                status="fail",
                message=f"Sales Invoice '{invoice_id}' not found",
                status_code=404,
                http_status=404,
            )

        result = service.update_sales_invoice_status(invoice_id, action)

        frappe.db.commit()

        action_map = {"approved": "approved", "cancelled": "cancelled", "amend": "amended"}

        return send_response(
            status="success",
            message=f"Sales Invoice {action_map[action]} successfully.",
            data=result,
            status_code=200,
            http_status=200,
        )

    except frappe.exceptions.ValidationError as e:
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()

        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )

    except frappe.exceptions.PermissionError as e:
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()

        return send_response(
            status="fail", message=f"You do not have permission to {action} the status of this Sales Invoice.Please contact your Administrator.", status_code=403, http_status=403
        )

    except zra_exception.ZRAConnectionError as e:

        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )
    
    except zra_exception.ZRAResponseError as e:

        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )

    except Exception as e:
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(), "Update Sales Invoice Status API Error"
        )
        return send_response(
            status="error",
            message="Internal Server Error",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["POST"])
@require_permission("Sales Invoice", "create")
def create_credit_note_from_si():
    invoice_id = frappe.request.args.get("invoice_id") or frappe.request.args.get("id")

    if not invoice_id:
        return send_response(
            status="fail",
            message="id is required as query parameter (?id=...)",
            status_code=400,
            http_status=400,
        )

    if not frappe.db.exists("Sales Invoice", invoice_id):
        return send_response(
            status="fail",
            message="Sales Invoice not found",
            status_code=404,
            http_status=404,
        )

    try:
        credit_note_doc = make_sales_return(invoice_id)

        default_payment_mode = None
        company_name = credit_note_doc.company or frappe.defaults.get_user_default("Company")
        company_doc = frappe.get_doc("Company", company_name)
        if company_doc.custom_extended_details:
            extended_details = company_doc.custom_extended_details[0]
            if extended_details.default_payment_mode:
                default_payment_mode = extended_details.default_payment_mode

        source_si = frappe.get_doc("Sales Invoice", invoice_id)
        source_payment_modes = {
            row.idx: row.payment_mode
            for row in (source_si.get("custom_details") or [])
        }

        for row in credit_note_doc.get("custom_details") or []:
            if not row.payment_mode:
                row.payment_mode = (
                    source_payment_modes.get(row.idx)
                    or (list(source_payment_modes.values())[0] if source_payment_modes else None)
                    or default_payment_mode
                )

        credit_note_doc.docstatus = 0
        credit_note_doc.insert(ignore_permissions=True)

        frappe.db.commit()

        return send_response(
            status="success",
            message="Credit Note created successfully from Sales Invoice",
            data={"id": credit_note_doc.name},
            status_code=201,
            http_status=201,
        )

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Create Credit Note from SI API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )