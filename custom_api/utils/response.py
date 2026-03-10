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