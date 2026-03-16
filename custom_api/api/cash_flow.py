
import frappe
from erpnext.accounts.report.cash_flow.cash_flow import execute
from custom_api.utils.response import send_response

def get_summary_with_colors(report_summary):
    colored_summary = []
    for item in report_summary:
        value = item.get("value", 0)

        if value > 0:
            color = "green"
        elif value < 0:
            color = "red"
        else:
            color = "gray"

        colored_summary.append({
            "label": item.get("label"),
            "value": value,
            "datatype": item.get("datatype"),
            "currency": item.get("currency"),
            "color": color
        })

    return colored_summary

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_cash_flow():
    company = frappe.defaults.get_user_default("Company")
    current_year = frappe.utils.now_datetime().year
    period_start_date = frappe.request.args.get("from_date", None)   #
    period_end_date = frappe.request.args.get("to_date", None)       #
    periodicity = frappe.request.args.get("periodicity", "Yearly")   #
    from_fiscal_year = frappe.request.args.get("from_fiscal_year", current_year)    #
    to_fiscal_year = frappe.request.args.get("to_fiscal_year", current_year)        #
    filter_based_on = frappe.request.args.get("filter_based_on", "Fiscal Year")

    filters = frappe._dict({
        "company": company,
        "from_fiscal_year": from_fiscal_year,
        "to_fiscal_year": to_fiscal_year,
        "period_start_date": period_start_date,
        "period_end_date": period_end_date,
        "filter_based_on": filter_based_on,
        "periodicity": periodicity,
        "include_default_book_entries": 0,
    })
    columns, data, _, chart, report_summary = execute(filters)

    return send_response(
        status="success",
        message="Profit and Loss fetched successfully.",
        data={
            "columns": columns,
            "summary": get_summary_with_colors(report_summary),
            "data": data
        },
        status_code=200,
        http_status=200,
    )