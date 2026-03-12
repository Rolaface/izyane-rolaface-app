from erpnext.setup.demo import get_warehouse
import frappe
from custom_api.utils.response import send_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_all_warehouse():
    company = frappe.defaults.get_user_default("Company")
    ware_house = get_warehouse(company)
    return send_response(
        status="success",
        message="Warehouse fetched successfully.",
        data={
            "ware_house": ware_house
        },
        status_code=200,
        http_status=200,
    )