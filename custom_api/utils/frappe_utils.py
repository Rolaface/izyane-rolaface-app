import frappe
from erpnext.accounts.utils import get_fiscal_year
from custom_api.utils.response import send_response


@frappe.whitelist()
def get_current_fiscal_year():
    try:
        today = frappe.utils.nowdate()
        company = frappe.defaults.get_user_default("Company")

        if not company:
            return send_response(
                status="fail",
                message="Company not set for user.",
                data=None,
                status_code=400,
                http_status=400,
            )

        fy, fy_start, fy_end = get_fiscal_year(today, company=company)

        return send_response(
            status="success",
            message="Current Fiscal Year fetched successfully.",
            data={
                "fiscal_year": fy,
                "start_date": fy_start,
                "end_date": fy_end
            },
            status_code=200,
            http_status=200,
        )

    except frappe.ValidationError:
        return send_response(
            status="fail",
            message="No active Fiscal Year found for the selected company.",
            data=None,
            status_code=404,
            http_status=404,
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Get Current Fiscal Year Failed")

        return send_response(
            status="fail",
            message="Something went wrong while fetching Fiscal Year.",
            data=None,
            status_code=500,
            http_status=500,
        )