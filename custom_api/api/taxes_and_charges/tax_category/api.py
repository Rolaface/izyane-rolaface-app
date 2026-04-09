from custom_api.api.taxes_and_charges.tax_category.service import create_tax_category_service, get_tax_categories_service, update_tax_category_service
from custom_api.utils.response import send_old_response, send_response_list
import frappe

@frappe.whitelist(methods=["POST"])
def create():
    try:
        data = frappe.request.get_json()

        result = create_tax_category_service(data)

        return send_old_response(
            status="success",
            message="Tax Category created successfully",
            data=result,
            status_code=200,
            http_status=200
        )
    except Exception as e:
        frappe.log_error(str(e), "Create Tax Category API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["PUT"])
def update():
    try:
        data = frappe.request.get_json()

        result = update_tax_category_service(data)

        return send_old_response(
            status="success",
            message="Tax Category updated successfully",
            data=result,
            status_code=200,
            http_status=200
        )
    except Exception as e:
        frappe.log_error(str(e), "Update Tax Category API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["GET"])
def get():
    try:
        args = frappe.local.form_dict

        result = get_tax_categories_service(args)

        return send_response_list(
            message="Tax Categories fetched successfully",
            data=result,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(str(e), "Get Tax Categories API Error")

        return send_response_list(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )