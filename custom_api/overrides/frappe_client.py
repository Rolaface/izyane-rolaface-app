import frappe
from frappe.client import delete as original_delete

@frappe.whitelist(methods=["DELETE", "POST"])
def delete(doctype, name):
    """
    Wrapper around frappe.client.delete that intercepts permission
    errors and returns a clean, user-friendly message.
    """
    try:
        return original_delete(doctype=doctype, name=name)

    except frappe.PermissionError as e:
        raw_message = f"You do not have permission to delete {doctype}."

        frappe.local.response.update({
            "status_code": 403,
            "status":      "fail",
            "message":     raw_message,
        })
        frappe.local.response.http_status_code = 403
        return

    except frappe.DoesNotExistError:
        frappe.local.response.update({
            "status_code": 404,
            "status":      "fail",
            "message":     f"{doctype} '{name}' not found.",
        })
        frappe.local.response.http_status_code = 404
        return

    except Exception as e:
        frappe.log_error(message=str(e), title=f"Delete {doctype} Error")
        frappe.local.response.update({
            "status_code": 500,
            "status": "fail",
            "message": str(e),
        })
        frappe.local.response.http_status_code = 500
        return