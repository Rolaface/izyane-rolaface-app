import frappe
from custom_api.utils.response import send_response, send_response_list

from .utils import get_arg, get_request_data
from . import service


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customer_groups():
    params = {
        "search": get_arg("search"),
        "parent_customer_group": get_arg("parent_customer_group"),
        "is_group": get_arg("is_group"),
        "as_tree": get_arg("as_tree", 1),
        "page": get_arg("page", 1),
        "page_size": get_arg("page_size", 100),
    }

    data = service.get_customer_groups(params)

    return send_response_list(
        status="success",
        message="Customer Groups fetched successfully.",
        data=data,
        status_code=200,
        http_status=200,
    )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customer_group(id):
    if not id:
        return send_response(
            status="error",
            message="Record ID (id) is required.",
            status_code=400,
            http_status=400
        )

    try:
        data = service.get_customer_group_by_id(id)

        return send_response(
            status="success",
            message="Record fetched successfully.",
            data=data,
            status_code=200,
            http_status=200,
        )

    except frappe.DoesNotExistError:
        return send_response(
            status="error",
            message=f"Customer Group '{id}' not found.",
            status_code=404,
            http_status=404
        )


@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_customer_group():
    data = get_request_data()

    if not data.get("customer_group_name"):
        return send_response(
            status="error",
            message="Missing required field: customer_group_name",
            status_code=400,
            http_status=400
        )

    try:
        result = service.create_customer_group(data)

        return send_response(
            status="success",
            message="Customer Group created successfully.",
            data=result,
            status_code=201,
            http_status=201,
        )

    except frappe.UniqueValidationError:
        return send_response(
            status="error",
            message="A Customer Group with this name already exists.",
            status_code=409,
            http_status=409
        )


@frappe.whitelist(allow_guest=False, methods=["POST", "PUT", "PATCH"])
def update_customer_group(id=None, **kwargs):
    data = get_request_data()
    record_id = id or data.get("id") or get_arg("id")

    if not record_id:
        return send_response(
            status="error",
            message="Record ID (id) is required.",
            status_code=400,
            http_status=400
        )

    try:
        result = service.update_customer_group(record_id, data)

        return send_response(
            status="success",
            message="Customer Group updated successfully.",
            data=result,
            status_code=200,
            http_status=200,
        )

    except frappe.DoesNotExistError:
        return send_response(
            status="error",
            message=f"Customer Group '{record_id}' not found.",
            status_code=404,
            http_status=404
        )


@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_customer_group(id):
    if not id:
        return send_response(
            status="error",
            message="Record ID (id) is required.",
            status_code=400,
            http_status=400
        )

    try:
        result = service.delete_customer_group(id)

        return send_response(
            status="success",
            message=f"Customer Group '{id}' deleted successfully.",
            data=result,
            status_code=200,
            http_status=200,
        )

    except frappe.DoesNotExistError:
        return send_response(
            status="error",
            message=f"Customer Group '{id}' not found.",
            status_code=404,
            http_status=404
        )