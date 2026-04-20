from custom_api.utils.response import send_old_response
import frappe
from frappe.utils import flt

@frappe.whitelist(allow_guest=False, methods=["GET"])
def summary():
    try:
        company = frappe.defaults.get_user_default("Company")
        current_year = frappe.utils.now_datetime().year
        total_customers = frappe.db.count("Customer", {"disabled": 0})
        total_suppliers = frappe.db.count("Supplier", {"disabled": 0})
        total_sales_invoices = frappe.db.count("Sales Invoice", {"docstatus": 1, "company": company})
        total_purchase_invoices = frappe.db.count("Purchase Invoice", {"docstatus": 1, "company": company})

        totals = frappe.db.sql("""
            SELECT
                COALESCE(SUM(base_grand_total), 0) AS base_grand_total,
                COALESCE(SUM(grand_total), 0)      AS grand_total
            FROM `tabSales Invoice`
            WHERE docstatus = 1
              AND company   = %(company)s
        """, {"company": company}, as_dict=True)

        totals = totals[0] if totals else {"base_grand_total": 0, "grand_total": 0}

        recent_sales = frappe.db.get_all(
            "Sales Invoice",
            filters={"docstatus": 1, "company": company},
            fields=["name", "customer", "posting_date", "base_grand_total", "status"],
            order_by="posting_date desc",
            limit=5,
        )

        monthly_sales = frappe.db.sql("""
            SELECT
                MONTH(posting_date)        AS month,
                COALESCE(SUM(base_grand_total), 0) AS total
            FROM `tabSales Invoice`
            WHERE docstatus    = 1
              AND company      = %(company)s
              AND YEAR(posting_date) = %(year)s
            GROUP BY MONTH(posting_date)
            ORDER BY MONTH(posting_date) ASC
        """, {"company": company, "year": current_year}, as_dict=True)

        monthly_sales_data = [0.0] * 12
        for row in monthly_sales:
            monthly_sales_data[row.month - 1] = flt(row.total)

        months_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        return send_old_response(
            status="success",
            message="Summary retrieved successfully.",
            data={
                "totalCustomers"        : total_customers,
                "totalSuppliers"        : total_suppliers,
                "totalSalesInvoices"    : total_sales_invoices,
                "totalPurchaseInvoices" : total_purchase_invoices,
                "totalSalesAmount"      : flt(totals["base_grand_total"]),
                "totalGrandAmount"      : flt(totals["grand_total"]),
                "recentSales"           : recent_sales,
                "monthlySalesGraph"     : {
                    "labels": months_labels,
                    "data"  : monthly_sales_data,
                },
            },
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Dashboard Summary API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving summary: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )
