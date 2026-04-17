import frappe
from custom_api.utils.response import send_response
from . import service

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