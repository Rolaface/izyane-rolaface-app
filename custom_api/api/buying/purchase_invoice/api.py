from custom_api.utils.response import send_response_list
import frappe
from custom_api.api.buying.purchase_invoice.service import get_purchase_invoice_list

@frappe.whitelist(allow_guest = False, methods=["GET"])
def get():
    data = frappe.local.form_dict

    try:
        response =  get_purchase_invoice_list(
                                        filters=data,
                                        page=int(data.get("page", 1)),
                                        page_size=int(data.get("page_size", 10)),
                                        search=data.get("search", "")
                                    )
        return send_response_list(
            status="success",
            message="Purchase Invoices retrieved successfully",
            data=response,
            status_code=200,
            http_status=200
        )
    except Exception as e:
        frappe.log_error(str(e), "Get Purchase Invoices API Error")

        return send_response_list(
            status="fail",
            message=str(e),
            data=[],
            status_code=500,
            http_status=500
        )