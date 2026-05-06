import frappe
from functools import wraps

def require_permission(doctype, action):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not frappe.has_permission(doctype=doctype, ptype=action):
                frappe.local.response = frappe._dict({
                    "status_code": 403,
                    "status": "fail",
                    "message": f"You do not have permission to {action} {doctype}. Please contact your Administrator.",
                })
                frappe.local.response.http_status_code = 403
                return
            return func(*args, **kwargs)
        return wrapper
    return decorator