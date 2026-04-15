import frappe
from custom_api.utils.response import send_response, send_response_list
from .utils import validate_journal_entry_payload
from ....utils.party_utils import parse_api_payload
from . import service

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_journal_entry():
    try:
        data = parse_api_payload()
        validate_journal_entry_payload(data)

        jv = service.create_journal_entry(data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Journal Entry created successfully.",
            data={"journalEntryId": jv.name, "difference": jv.difference},
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
        frappe.log_error(frappe.get_traceback(), "Create Journal Entry API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_journal_entry(id=None):
    try:
        data = parse_api_payload()
        jv_id = id or frappe.request.args.get("id")

        if not jv_id:
            return send_response(
                status="fail",
                message="Journal Entry ID required as query parameter (?id=...)",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Journal Entry", jv_id):
            return send_response(
                status="fail",
                message="Journal Entry not found",
                status_code=404,
                http_status=404,
            )

        validate_journal_entry_payload(data, is_update=True)
        jv = service.update_journal_entry(jv_id, data)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Journal Entry updated successfully",
            data={"journalEntryId": jv.name, "difference": jv.difference},
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
        frappe.log_error(frappe.get_traceback(), "Update Journal Entry API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_journal_entry_by_id(id):
    try:
        if not frappe.db.exists("Journal Entry", id):
            return send_response(
                status="fail",
                message="Journal Entry not found",
                status_code=404,
                http_status=404,
            )

        data = service.get_journal_entry_by_id(id)
        return send_response(
            status="success",
            message="Journal Entry retrieved successfully",
            status_code=200,
            data=data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Journal Entry By ID Error")
        return send_response(
            status="error",
            message=f"Failed to retrieve entry: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_journal_entries(page=1, page_size=20):
    data = frappe.local.form_dict
    search = data.get("search")
    
    filters_str = data.get("filters")
    filters = frappe.parse_json(filters_str) if filters_str else {}

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

        entries, total_entries, total_pages = service.get_journal_entries(
            filters, page, page_size, search
        )

        response_data = {
            "success": True,
            "message": "Journal Entries retrieved successfully",
            "data": entries,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_entries,
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
        frappe.log_error(frappe.get_traceback(), "Get All Journal Entries Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_journal_entry(id=None):
    try:
        jv_id = id or frappe.local.form_dict.get("id")
        if not jv_id:
            return send_response(
                status="fail",
                message="Journal Entry ID required",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Journal Entry", jv_id):
            return send_response(
                status="fail",
                message="Journal Entry not found",
                status_code=404,
                http_status=404,
            )

        service.delete_journal_entry(jv_id)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Journal Entry deleted successfully",
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
        frappe.log_error(frappe.get_traceback(), "Delete Journal Entry Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
def update_journal_entry_status(id=None, action=None):
    try:
        jv_id = id or frappe.request.args.get("id")
        raw_action = action or frappe.request.args.get("action")

        if not jv_id:
            return send_response(
                status="fail",
                message="Journal Entry ID is required",
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

        if not frappe.db.exists("Journal Entry", jv_id):
            return send_response(
                status="fail",
                message=f"Journal Entry '{jv_id}' not found",
                status_code=404,
                http_status=404,
            )

        result = service.update_journal_entry_status(jv_id, action)

        frappe.db.commit()

        action_map = {"approved": "approved", "cancelled": "cancelled", "amend": "amended"}

        return send_response(
            status="success",
            message=f"Journal Entry {action_map[action]} successfully.",
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
            frappe.get_traceback(), "Update Journal Entry Status API Error"
        )
        return send_response(
            status="error",
            message="Internal Server Error",
            status_code=500,
            http_status=500,
        )