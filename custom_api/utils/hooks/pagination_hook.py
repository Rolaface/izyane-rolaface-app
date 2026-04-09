import json
import traceback
from typing import Optional, Any
from urllib.parse import unquote
import frappe
from frappe.utils import cint

DEFAULT_PAGE_LENGTH = 20
API_RESOURCE_PREFIX = "/api/resource/"

def _extract_doctype_from_path(path: str) -> Optional[str]:
    decoded_path = unquote(path)
    
    if not decoded_path.startswith(API_RESOURCE_PREFIX):
        return None
    
    path_parts = [p for p in decoded_path.split("/") if p]
    
    if len(path_parts) != 3:
        return None
        
    return path_parts[2]

def _parse_request_filters() -> Any:
    raw_filters = frappe.form_dict.get("filters")
    
    if not raw_filters or not isinstance(raw_filters, str):
        return raw_filters

    try:
        return json.loads(raw_filters)
    except json.JSONDecodeError:
        return None

def inject_pagination_metadata(**kwargs) -> None:
    response = kwargs.get("response")

    if not getattr(frappe.local, "request", None) or frappe.request.method != "GET":
        return

    if not cint(frappe.form_dict.get("with_pagination")):
        return

    doctype = _extract_doctype_from_path(frappe.request.path)
    if not doctype:
        return

    if not response or response.mimetype != "application/json" or response.status_code != 200:
        return

    try:
        response_data = json.loads(response.get_data(as_text=True))
        if "data" not in response_data:
            return

        page_size = cint(frappe.form_dict.get("limit_page_length", DEFAULT_PAGE_LENGTH))
        page_size = page_size if page_size > 0 else DEFAULT_PAGE_LENGTH
        
        limit_start = cint(frappe.form_dict.get("limit_start", 0))
        current_page = (limit_start // page_size) + 1

        filters = _parse_request_filters()
        total_records = frappe.db.count(doctype, filters=filters)

        total_pages = max(1, (total_records + page_size - 1) // page_size)
        has_next = current_page < total_pages
        has_prev = current_page > 1

        from custom_api.utils.response import send_response_list

        payload = {
            "data": response_data["data"],
            "pagination": {
                "page": current_page,
                "page_size": page_size,
                "total": total_records,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }

        final_envelope = send_response_list(
            status="success",
            message="Records retrieved successfully",
            data=payload,
            status_code=200,
            http_status=200
        )

        response.set_data(json.dumps(frappe.local.response))
        # response.set_data(json.dumps(final_envelope))

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Pagination Hook Error - {doctype}")
        
        error_payload = {
            "status_code": 500,
            "status": "error",
            "message": f"Failed to attach pagination: {str(e)}",
            "data": None
        }
        
        response.set_data(json.dumps(error_payload))
        response.status_code = 500