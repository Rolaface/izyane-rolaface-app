from custom_api.utils.response import send_old_response
import frappe
from frappe.utils import flt, cint, nowdate
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
def dashboard_summary():
    try:
        # 1. Setup Common Variables
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")
        today = nowdate()

        si = frappe.qb.DocType("Sales Invoice")
        pi = frappe.qb.DocType("Purchase Invoice")

        # ==========================================
        # 2. Sales Queries
        # ==========================================
        sales_data = (
            frappe.qb.from_(si)
            .select(Sum(si.base_grand_total).as_("total"), Count(si.name).as_("count"))
            .where(si.docstatus == 1).where(si.company == company)
        ).run(as_dict=True)

        sales_outstanding_data = (
            frappe.qb.from_(si)
            .select(Sum(si.outstanding_amount * si.conversion_rate).as_("total"), Count(si.name).as_("count"))
            .where(si.docstatus == 1).where(si.company == company).where(si.outstanding_amount > 0)
        ).run(as_dict=True)

        sales_overdue_data = (
            frappe.qb.from_(si)
            .select(Sum(si.outstanding_amount * si.conversion_rate).as_("total"), Count(si.name).as_("count"))
            .where(si.docstatus == 1).where(si.company == company)
            .where(si.due_date < today).where(si.outstanding_amount > 0)
        ).run(as_dict=True)

        # ==========================================
        # 3. Purchase Queries
        # ==========================================
        purchase_data = (
            frappe.qb.from_(pi)
            .select(Sum(pi.base_grand_total).as_("total"), Count(pi.name).as_("count"))
            .where(pi.docstatus == 1).where(pi.company == company)
        ).run(as_dict=True)

        purchase_outstanding_data = (
            frappe.qb.from_(pi)
            .select(Sum(pi.outstanding_amount * pi.conversion_rate).as_("total"), Count(pi.name).as_("count"))
            .where(pi.docstatus == 1).where(pi.company == company).where(pi.outstanding_amount > 0)
        ).run(as_dict=True)

        purchase_overdue_data = (
            frappe.qb.from_(pi)
            .select(Sum(pi.outstanding_amount * pi.conversion_rate).as_("total"), Count(pi.name).as_("count"))
            .where(pi.docstatus == 1).where(pi.company == company)
            .where(pi.due_date < today).where(pi.outstanding_amount > 0)
        ).run(as_dict=True)

        # ==========================================
        # 4. Customer & Supplier Queries
        # ==========================================
        total_customers = frappe.db.count("Customer")
        active_customers = frappe.db.count("Customer", {"disabled": 0})
        inactive_customers = frappe.db.count("Customer", {"disabled": 1})

        total_suppliers = frappe.db.count("Supplier")
        active_suppliers = frappe.db.count("Supplier", {"disabled": 0})
        inactive_suppliers = frappe.db.count("Supplier", {"disabled": 1})

        # ==========================================
        # 5. Compile and Return Final Dictionary
        # ==========================================
        summary_data = {
            "sales": {
                "totalSales": flt(sales_data[0].total) if sales_data else 0.0,
                "salesCount": cint(sales_data[0].count) if sales_data else 0,
                "totalOutstanding": flt(sales_outstanding_data[0].total) if sales_outstanding_data else 0.0,
                "outstandingCount": cint(sales_outstanding_data[0].count) if sales_outstanding_data else 0,
                "totalOverdue": flt(sales_overdue_data[0].total) if sales_overdue_data else 0.0,
                "overdueCount": cint(sales_overdue_data[0].count) if sales_overdue_data else 0
            },
            "purchase": {
                "totalPurchase": flt(purchase_data[0].total) if purchase_data else 0.0,
                "purchaseCount": cint(purchase_data[0].count) if purchase_data else 0,
                "totalOutstanding": flt(purchase_outstanding_data[0].total) if purchase_outstanding_data else 0.0,
                "outstandingCount": cint(purchase_outstanding_data[0].count) if purchase_outstanding_data else 0,
                "totalOverdue": flt(purchase_overdue_data[0].total) if purchase_overdue_data else 0.0,
                "overdueCount": cint(purchase_overdue_data[0].count) if purchase_overdue_data else 0
            },
            "customer": {
                "totalCustomers": total_customers,
                "activeCustomers": active_customers,
                "inactiveCustomers": inactive_customers
            },
            "supplier": {
                "totalSuppliers": total_suppliers,
                "activeSuppliers": active_suppliers,
                "inactiveSuppliers": inactive_suppliers
            }
        }

        return send_old_response(
            status="success",
            message="Dashboard summary retrieved successfully.",
            data=summary_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Dashboard Summary API Error")
        
        return send_old_response(
            status="error",
            message=f"Error retrieving dashboard summary: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )





