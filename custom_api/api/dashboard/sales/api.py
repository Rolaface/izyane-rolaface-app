import frappe
from custom_api.utils.response import send_old_response
from frappe.utils import flt, getdate

@frappe.whitelist(allow_guest=False, methods=["GET"])
def top_recent_sales():
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        # Fetch the top 10 most recent submitted invoices
        recent_sales = frappe.get_all(
            "Sales Invoice",
            filters={
                "docstatus": 1,
                "company": company
            },
            fields=[
                "name", 
                "customer_name", 
                "posting_date", 
                "base_grand_total", 
                "outstanding_amount", 
                "status",
                "currency" # Helpful if you want to display the currency symbol on the frontend
            ],
            order_by="posting_date desc, creation desc",
            limit_page_length=10
        )

        return send_old_response(
            status="success",
            message="Top 10 recent sales retrieved successfully.",
            data=recent_sales,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Recent Sales API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving recent sales data: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def monthly_sales_breakdown(year=None):
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        filters = {
            "docstatus": 1,
            "company": company
        }

        # Apply year filter if provided
        if year:
            filters["posting_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]

        # Fetch relevant invoice data
        invoices = frappe.get_all(
            "Sales Invoice",
            filters=filters,
            fields=["posting_date", "base_grand_total", "outstanding_amount", "conversion_rate"]
        )

        # ==========================================
        # 1. Initialize 12 Months Array
        # ==========================================
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # This structure matches the frontend ECharts expectation
        chart_data = [
            {"month": m, "totalSales": 0.0, "totalReceived": 0.0, "totalPending": 0.0} 
            for m in months
        ]

        # ==========================================
        # 2. Populate Array with Data
        # ==========================================
        for inv in invoices:
            if not inv.posting_date:
                continue
                
            # Get the month index (0 to 11)
            month_idx = getdate(inv.posting_date).month - 1 
            
            # Calculate amounts in base currency
            sales_amount = flt(inv.base_grand_total)
            
            # Ensure conversion_rate fallback to 1 to avoid multiplying by 0
            conversion_rate = flt(inv.conversion_rate) or 1.0 
            pending_amount = flt(inv.outstanding_amount) * conversion_rate
            
            received_amount = sales_amount - pending_amount

            # Add to the respective month's totals
            if 0 <= month_idx < 12:
                chart_data[month_idx]["totalSales"] += sales_amount
                chart_data[month_idx]["totalPending"] += pending_amount
                chart_data[month_idx]["totalReceived"] += received_amount

        # ==========================================
        # 3. Return Final Data
        # ==========================================
        return send_old_response(
            status="success",
            message="Monthly sales breakdown retrieved successfully.",
            data=chart_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Monthly Sales Breakdown API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving sales breakdown: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )