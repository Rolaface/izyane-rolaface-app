from custom_api.utils.response import send_old_response
import frappe
from frappe.utils import flt, nowdate, cint
from frappe.query_builder.functions import Sum, Count

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

@frappe.whitelist(allow_guest=False, methods=["GET"])
def sales_summary():
    try:
        # Get the default company for the logged-in user
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")
        today = nowdate()

        # Initialize the DocType for Query Builder
        si = frappe.qb.DocType("Sales Invoice")

        # 1. Fetch Total Sales Amount & Total Sales Count
        sales_data = (
            frappe.qb.from_(si)
            .select(
                Sum(si.base_grand_total).as_("total_sales"),
                Count(si.name).as_("sales_count")
            )
            .where(si.docstatus == 1)
            .where(si.company == company)
        ).run(as_dict=True)

        # 2. Fetch Total Outstanding Amount & Outstanding Invoice Count
        outstanding_data = (
            frappe.qb.from_(si)
            .select(
                Sum(si.outstanding_amount).as_("total_outstanding"),
                Count(si.name).as_("outstanding_count")
            )
            .where(si.docstatus == 1)
            .where(si.company == company)
            .where(si.outstanding_amount > 0)
        ).run(as_dict=True)

        # 3. Fetch Total Overdue Amount & Overdue Invoice Count
        overdue_data = (
            frappe.qb.from_(si)
            .select(
                Sum(si.outstanding_amount).as_("total_overdue"),
                Count(si.name).as_("overdue_count")
            )
            .where(si.docstatus == 1)
            .where(si.company == company)
            .where(si.due_date < today)
            .where(si.outstanding_amount > 0)
        ).run(as_dict=True)

        # Safely extract float (flt) amounts and integer (cint) counts
        total_sales = flt(sales_data[0].total_sales) if sales_data else 0.0
        sales_count = cint(sales_data[0].sales_count) if sales_data else 0
        
        total_outstanding = flt(outstanding_data[0].total_outstanding) if outstanding_data else 0.0
        outstanding_count = cint(outstanding_data[0].outstanding_count) if outstanding_data else 0
        
        total_overdue = flt(overdue_data[0].total_overdue) if overdue_data else 0.0
        overdue_count = cint(overdue_data[0].overdue_count) if overdue_data else 0

        return send_old_response(
            status="success",
            message="Sales summary retrieved successfully.",
            data={
                "totalSales": total_sales,
                "salesCount": sales_count,
                "totalOutstanding": total_outstanding,
                "outstandingCount": outstanding_count,
                "totalOverdue": total_overdue,
                "overdueCount": overdue_count
            },
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Sales Summary API Error")
        
        return send_old_response(
            status="error",
            message=f"Error retrieving sales summary: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )