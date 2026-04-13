from custom_api.utils.response import send_response_list
import frappe
from .service import get_address_list_service

@frappe.whitelist()
def get_address_list(
    company=None,
    customer=None,
    supplier=None,
    addressType=None,
    search=None
):
    response =  get_address_list_service(
                        company=company,
                        customer=customer,
                        supplier=supplier,
                        address_type=addressType,
                        search=search
                )

    return send_response_list(
        status="success",
        message="Addresses retrieved successfully",
        data=response,
        status_code=200,
        http_status=200
    )