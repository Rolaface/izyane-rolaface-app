import frappe
from custom_api.utils.response import send_response, send_response_list
from .utils import validate_rfq_payload
from ....utils.party_utils import parse_api_payload
from . import service

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_rfq():
    try:
        data = parse_api_payload()
        validate_rfq_payload(data)

        rfq = service.create_rfq(data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="RFQ created successfully.",
            data={"rfqId": rfq.name},
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
        frappe.log_error(frappe.get_traceback(), "Create RFQ API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_rfq(id=None, **kwargs):
    try:
        data = parse_api_payload()
        rfq_id = id or frappe.request.args.get("id")

        if not rfq_id:
            return send_response(
                status="fail",
                message="RFQ ID required as query parameter (?id=...)",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Request for Quotation", rfq_id):
            return send_response(
                status="fail",
                message="RFQ not found",
                status_code=404,
                http_status=404,
            )

        validate_rfq_payload(data, is_update=True)
        service.update_rfq(rfq_id, data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="RFQ updated successfully",
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
        frappe.log_error(frappe.get_traceback(), "Update RFQ API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_rfq_by_id(id):
    try:
        if not frappe.db.exists("Request for Quotation", id):
            return send_response(
                status="fail",
                message="RFQ not found",
                status_code=404,
                http_status=404,
            )

        data = service.get_rfq_by_id(id)
        return send_response(
            status="success",
            message="RFQ retrieved successfully",
            status_code=200,
            data=data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get RFQ By ID Error")
        return send_response(
            status="error",
            message=f"Failed to retrieve RFQ: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_rfqs(page=1, page_size=20):
    data = frappe.local.form_dict
    search = data.get("search")
    
    sort_by = data.get("sort_by", "creation")
    sort_order = data.get("sort_order", "desc")
    
    if sort_order.lower() not in ["asc", "desc"]:
        sort_order = "desc"

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

        rfqs, total_rfqs, total_pages = service.get_rfqs(
            data, page, page_size, search, sort_by, sort_order
        )

        response_data = {
            "success": True,
            "message": "RFQs retrieved successfully",
            "data": rfqs,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_rfqs,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "sort_by": sort_by,
                "sort_order": sort_order
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
        frappe.log_error(frappe.get_traceback(), "Get All RFQs Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_rfq(id=None):
    try:
        rfq_id = id or frappe.local.form_dict.get("id")
        if not rfq_id:
            return send_response(
                status="fail",
                message="RFQ ID required",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Request for Quotation", rfq_id):
            return send_response(
                status="fail",
                message="RFQ not found",
                status_code=404,
                http_status=404,
            )

        service.delete_rfq(rfq_id)
        frappe.db.commit()
        return send_response(
            status="success",
            message="RFQ deleted successfully",
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
        frappe.log_error(frappe.get_traceback(), "Delete RFQ Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_rfq_status(id=None, action=None):
    try:
        rfq_id = id or frappe.request.args.get("id")
        raw_action = action or frappe.request.args.get("action")

        if not rfq_id:
            return send_response(
                status="fail",
                message="RFQ ID is required",
                status_code=400,
                http_status=400,
            )

        if not raw_action:
            return send_response(
                status="fail",
                message="Action is required (submitted, cancelled, amend)",
                status_code=400,
                http_status=400,
            )

        action = str(raw_action).strip().lower()

        if action not in {"submitted", "cancelled", "amend"}:
            return send_response(
                status="fail",
                message=f"Invalid action '{raw_action}'. Allowed values: submitted, cancelled, amend",
                status_code=400,
                http_status=400,
            )

        if not frappe.db.exists("Request for Quotation", rfq_id):
            return send_response(
                status="fail",
                message=f"RFQ '{rfq_id}' not found",
                status_code=404,
                http_status=404,
            )

        result = service.update_rfq_status(rfq_id, action)

        frappe.db.commit()

        action_map = {"submitted": "submitted", "cancelled": "cancelled", "amend": "amended"}

        return send_response(
            status="success",
            message=f"RFQ {action_map[action]} successfully.",
            data=result,
            status_code=200,
            http_status=200,
        )

    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(
            status="fail", message=str(e), status_code=400, http_status=400
        )

    except frappe.exceptions.PermissionError as e:
        frappe.db.rollback()
        return send_response(
            status="fail", message=str(e), status_code=403, http_status=403
        )

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(), "Update RFQ Status API Error"
        )
        return send_response(
            status="error",
            message="Internal Server Error",
            status_code=500,
            http_status=500,
        )