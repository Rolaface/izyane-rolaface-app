import frappe

def send_response(status, message, data=None, status_code=200, http_status=200):
    frappe.response["http_status_code"] = http_status
    return {
        "status_code": status_code,
        "status": status,
        "message": message,
        "data": data
    }

def send_response_list(status, message, data=None, status_code=200, http_status=200):
    frappe.response["http_status_code"] = http_status
    return {
        "status_code": status_code,
        "status": status,
        "message": message,
        **data
    }

def send_old_response(status="success", message="", data=None, status_code = None , http_status=200):

    if  not data:
        frappe.local.response = frappe._dict({

            "status_code": status_code, 
            "status": status,
            "message": message,
        })
        frappe.local.response.http_status_code = http_status

    else:
        frappe.local.response = frappe._dict({

            "status_code": status_code, 
            "status": status,
            "message": message,
            "data": data
        })
        frappe.local.response.http_status_code = http_status


def send_response_list(status="success", message="", data=None, status_code=200, http_status=200):

    response_payload = {
        "status_code": status_code,
        "status": status,
        "message": message
    }

    if data is not None:
        if isinstance(data, dict) and "data" in data:
            response_payload["data"] = data.get("data", [])
            if "pagination" in data:
                response_payload["pagination"] = data.get("pagination", {})
        elif isinstance(data, list):
            response_payload["data"] = data
        else:
            response_payload["data"] = data

    frappe.local.response = frappe._dict(response_payload)
    frappe.local.response.http_status_code = http_status
    
    
def send_response_list_sale(status="success", message="", data=None, pagination=None, status_code=200, http_status=200):
    response_payload = {
        "status_code": status_code,
        "status": status,
        "message": message,
        "data": data if data is not None else []
    }

    if pagination:
        response_payload["pagination"] = pagination

    frappe.local.response = frappe._dict(response_payload)
    frappe.local.response.http_status_code = http_status
    
def handle_api_error(e: Exception, context_message: str):
    frappe.db.rollback()
    
    if not isinstance(e, (frappe.ValidationError, frappe.DuplicateEntryError, frappe.DoesNotExistError)):
        frappe.log_error(frappe.get_traceback(), context_message)

    error_message = str(e).strip()
    import re
    error_message = re.sub('<[^<]+?>', '', error_message)

    status_code = 500
    status_type = "error"

    if isinstance(e, frappe.DoesNotExistError):
        status_code = 404
        status_type = "fail"
    elif isinstance(e, frappe.DuplicateEntryError):
        status_code = 409
        status_type = "fail"
    elif isinstance(e, frappe.PermissionError):
        status_code = 403
        status_type = "fail"
        error_message = "You do not have permission to perform this action."
    elif isinstance(e, frappe.ValidationError):
        status_code = 400
        status_type = "fail"
    
    return send_response(
        status=status_type,
        message=error_message,
        status_code=status_code,
        http_status=status_code,
    )