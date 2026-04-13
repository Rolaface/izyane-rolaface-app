import frappe
from custom_api.utils.response import send_old_response, send_response_list
from custom_api.api.taxes_and_charges.sales.service import (
    delete_sales_tax_template_service,
    get_sales_tax_template_service,
    get_sales_tax_templates_service, 
    update_sales_tax_status_service, 
    create_sales_tax_template_service,
    update_sales_tax_template_service
)

@frappe.whitelist(methods=["POST"])
def create_sales_tax_template():
    try:
        data = frappe.request.get_json()

        result = create_sales_tax_template_service(data)

        return send_old_response(
            status="success",
            message="Sales Tax Template created successfully",
            data=result,
            status_code=201,
            http_status=201
        )

    except Exception as e:
        frappe.log_error(message=str(e), title="Create Sales Tax API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["PUT", "PATCH"])
def update_sales_tax_template():
    try:
        template_name = frappe.request.args.get("name")
        data = frappe.request.get_json()
        
        is_patch = frappe.request.method == "PATCH"

        result = update_sales_tax_template_service(template_name, data, is_patch)

        return send_old_response(
            status="success",
            message=f"Sales Tax Template updated successfully",
            data=result,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(message=str(e), title="Update/Patch Sales Tax API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["GET"])
def get_sales_tax_templates():
    try:
        args = frappe.local.form_dict

        data = get_sales_tax_templates_service(args)

        return send_response_list(
            status="success",
            message="Sales Tax Templates retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(str(e), "Get Sales Tax Templates API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["PUT"])
def update_sales_tax_status():
    try:
        template_name = frappe.request.args.get("name")
        data = frappe.request.get_json()

        result = update_sales_tax_status_service(data, template_name)

        return send_old_response(
            status="success",
            message="Sales Tax Template status updated successfully",
            data=result
        )

    except Exception as e:
        frappe.log_error(str(e), "Update Sales Tax Status API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(methods=["GET"])
def get_sales_tax_template(name):
    try:
        if not name:
            frappe.throw("Parameter 'name' is required to fetch the template.")

        data = get_sales_tax_template_service(name)

        return send_old_response(
            status="success",
            message="Sales Tax Template retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(str(e), "Get Sales Tax Template By ID API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )
    
@frappe.whitelist(methods=["DELETE"])
def delete_sales_tax_template(name):
    try:
        if not name:
            frappe.throw("Parameter 'name' is required to delete the template.")

        result = delete_sales_tax_template_service(name)

        return send_old_response(
            status="success",
            message="Sales Tax Template deleted successfully",
            data=result,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(str(e), "Delete Sales Tax Template API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )