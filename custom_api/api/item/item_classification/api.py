import frappe
from custom_api.permission import require_permission
from custom_api.utils.response import send_response, send_response_list
from custom_api.utils.party_utils import parse_api_payload
from .utils import validate_classification_payload
from . import service


@frappe.whitelist(allow_guest=False, methods=["POST"])
# @require_permission("Custom Item Classification", "create")
def create_classification():
    try:
        data = parse_api_payload()
        validate_classification_payload(data)

        classification = service.create_classification(data)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Custom Item Classification created successfully.",
            data={"id": classification.name},
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
        frappe.log_error(frappe.get_traceback(), "Create Custom Item Classification API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["PUT", "PATCH"])
# @require_permission("Custom Item Classification", "write")
def update_classification(id=None, **kwargs):
    try:
        data = parse_api_payload()
        classification_id = id or frappe.request.args.get("id")

        if not classification_id:
            return send_response(
                status="fail",
                message="Classification ID required as query parameter (?id=...)",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Custom Item Classification", classification_id):
            return send_response(
                status="fail",
                message="Custom Item Classification not found",
                status_code=404,
                http_status=404,
            )

        validate_classification_payload(data, is_update=True)
        service.update_classification(classification_id, data)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Custom Item Classification updated successfully",
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
        frappe.log_error(frappe.get_traceback(), "Update Custom Item Classification API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
# @require_permission("Custom Item Classification", "read")
def get_classification_by_id(id=None):
    try:
        classification_id = id or frappe.request.args.get("id")
        if not classification_id:
            return send_response(
                status="fail",
                message="Classification ID required",
                status_code=400,
                http_status=400,
            )

        if not frappe.db.exists("Custom Item Classification", classification_id):
            return send_response(
                status="fail",
                message="Custom Item Classification not found",
                status_code=404,
                http_status=404,
            )

        data = service.get_classification_by_id(classification_id)
        return send_response(
            status="success",
            message="Custom Item Classification retrieved successfully",
            status_code=200,
            data=data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Custom Item Classification By ID Error")
        return send_response(
            status="error",
            message=f"Failed to retrieve classification: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
# @require_permission("Custom Item Classification", "read")
def get_classification_by_code(class_code=None):
    try:
        code = class_code or frappe.request.args.get("class_code")
        if not code:
            return send_response(
                status="fail",
                message="class_code is required as a parameter (?class_code=...)",
                status_code=400,
                http_status=400,
            )

        data = service.get_classification_by_code(code)
        if not data:
            return send_response(
                status="fail",
                message=f"Custom Item Classification with class_code '{code}' not found",
                status_code=404,
                http_status=404,
            )

        return send_response(
            status="success",
            message="Custom Item Classification retrieved successfully",
            status_code=200,
            data=data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Custom Item Classification By Code Error")
        return send_response(
            status="error",
            message=f"Failed to retrieve classification: {str(e)}",
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
# @require_permission("Custom Item Classification", "read")
def get_classifications(page=1, page_size=10):
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

        classifications, total_records, total_pages = service.get_classifications(
            data, page, page_size, search
        )

        response_data = {
            "success": True,
            "message": "Custom Item Classifications retrieved successfully",
            "data": classifications,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_records,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

        return send_response_list(
            status="success",
            message="Item Classifications retrieved successfully",
            status_code=200,
            data=response_data,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Custom Item Classifications Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
# @require_permission("Custom Item Classification", "read")
def get_classification_children(parent_code=None, page_size=50, cursor=None):
	"""Return one paginated level of the hierarchy.

	When parent_code is omitted, only active Level 1 classifications are returned.
	"""
	try:
		parent_code = parent_code or frappe.local.form_dict.get("parent_code")
		page_size = page_size or frappe.local.form_dict.get("page_size") or 50
		cursor = cursor or frappe.local.form_dict.get("cursor")
		items, pagination = service.get_classification_children(parent_code, page_size, cursor)
		return send_response_list(
			status="success",
			message="Classification children retrieved successfully",
			status_code=200,
			data={"data": items, "pagination": pagination},
			http_status=200,
		)
	except frappe.exceptions.ValidationError as e:
		return send_response(status="fail", message=str(e), status_code=400, http_status=400)
	except frappe.DoesNotExistError as e:
		return send_response(status="fail", message=str(e), status_code=404, http_status=404)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Classification Children API Error")
		return send_response(status="error", message="Failed to retrieve classification children", status_code=500, http_status=500)


@frappe.whitelist(allow_guest=False, methods=["GET"])
# @require_permission("Custom Item Classification", "read")
def search_classifications(search=None, page_size=30, cursor=None):
	"""Search active classifications and return their complete ancestor paths."""
	try:
		search = search if search is not None else frappe.local.form_dict.get("search")
		page_size = page_size or frappe.local.form_dict.get("page_size") or 30
		cursor = cursor or frappe.local.form_dict.get("cursor")
		items, pagination = service.search_classifications(search, page_size, cursor)
		return send_response_list(
			status="success",
			message="Classifications searched successfully",
			status_code=200,
			data={"data": items, "pagination": pagination},
			http_status=200,
		)
	except frappe.exceptions.ValidationError as e:
		return send_response(status="fail", message=str(e), status_code=400, http_status=400)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Search Classifications API Error")
		return send_response(status="error", message="Failed to search classifications", status_code=500, http_status=500)


@frappe.whitelist(allow_guest=False, methods=["DELETE"])
# @require_permission("Custom Item Classification", "delete")
def delete_classification(id=None):
    try:
        classification_id = id or frappe.local.form_dict.get("id")
        if not classification_id:
            return send_response(
                status="fail",
                message="Classification ID required",
                status_code=400,
                http_status=400,
            )
        if not frappe.db.exists("Custom Item Classification", classification_id):
            return send_response(
                status="fail",
                message="Custom Item Classification not found",
                status_code=404,
                http_status=404,
            )

        service.delete_classification(classification_id)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Custom Item Classification deleted successfully",
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
        frappe.log_error(frappe.get_traceback(), "Delete Custom Item Classification Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )
