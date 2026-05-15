from custom_api.utils.response import send_old_response
import frappe
from frappe.utils import flt, cint, nowdate, getdate
from frappe.query_builder.functions import Sum, Count, Extract
from frappe.query_builder import Order

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

        total_customers = frappe.db.count("Customer")
        active_customers = frappe.db.count("Customer", {"disabled": 0})
        inactive_customers = frappe.db.count("Customer", {"disabled": 1})

        total_suppliers = frappe.db.count("Supplier")
        active_suppliers = frappe.db.count("Supplier", {"disabled": 0})
        inactive_suppliers = frappe.db.count("Supplier", {"disabled": 1})

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

@frappe.whitelist(allow_guest=False, methods=["GET"])
def notes():
    try:
        # 1. Setup Common Variables
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")
        
        # Initialize DocTypes
        si = frappe.qb.DocType("Sales Invoice")
        pi = frappe.qb.DocType("Purchase Invoice")
        sii = frappe.qb.DocType("Sales Invoice Item")

        top_customer_query = (
            frappe.qb.from_(si)
            .select(si.customer_name, Sum(si.base_grand_total).as_("total_sales"))
            .where(si.docstatus == 1)
            .where(si.company == company)
            .groupby(si.customer)
            .orderby(Sum(si.base_grand_total), order=Order.desc)
            .limit(1)
        ).run(as_dict=True)

        top_customer = top_customer_query[0] if top_customer_query else None

        top_supplier_query = (
            frappe.qb.from_(pi)
            .select(pi.supplier_name, Sum(pi.base_grand_total).as_("total_purchases"))
            .where(pi.docstatus == 1)
            .where(pi.company == company)
            .groupby(pi.supplier)
            .orderby(Sum(pi.base_grand_total), order=Order.desc)
            .limit(1)
        ).run(as_dict=True)

        top_supplier = top_supplier_query[0] if top_supplier_query else None

        top_item_qty_query = (
            frappe.qb.from_(sii)
            .inner_join(si).on(sii.parent == si.name)
            .select(sii.item_code, sii.item_name, Sum(sii.qty).as_("total_qty"))
            .where(si.docstatus == 1)
            .where(si.company == company)
            .groupby(sii.item_code, sii.item_name)
            .orderby(Sum(sii.qty), order=Order.desc)
            .limit(1)
        ).run(as_dict=True)

        top_item_by_qty = top_item_qty_query[0] if top_item_qty_query else None

        top_item_val_query = (
            frappe.qb.from_(sii)
            .inner_join(si).on(sii.parent == si.name)
            .select(sii.item_code, sii.item_name, Sum(sii.base_amount).as_("total_value"))
            .where(si.docstatus == 1)
            .where(si.company == company)
            .groupby(sii.item_code, sii.item_name)
            .orderby(Sum(sii.base_amount), order=Order.desc)
            .limit(1)
        ).run(as_dict=True)

        top_item_by_value = top_item_val_query[0] if top_item_val_query else None

        notes_data = {
            "topCustomer": {
                "name": top_customer.customer_name if top_customer else "N/A",
                "value": flt(top_customer.total_sales) if top_customer else 0.0
            },
            "topSupplier": {
                "name": top_supplier.supplier_name if top_supplier else "N/A",
                "value": flt(top_supplier.total_purchases) if top_supplier else 0.0
            },
            "topSellingItemQty": {
                "itemCode": top_item_by_qty.item_code if top_item_by_qty else "N/A",
                "itemName": top_item_by_qty.item_name if top_item_by_qty else "N/A",
                "quantity": flt(top_item_by_qty.total_qty) if top_item_by_qty else 0.0
            },
            "topSellingItemValue": {
                "itemCode": top_item_by_value.item_code if top_item_by_value else "N/A",
                "itemName": top_item_by_value.item_name if top_item_by_value else "N/A",
                "value": flt(top_item_by_value.total_value) if top_item_by_value else 0.0
            }
        }

        return send_old_response(
            status="success",
            message="Notes retrieved successfully.",
            data=notes_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Dashboard Notes API Error")
        
        return send_old_response(
            status="error",
            message=f"Error retrieving notes: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def sales_chart(from_date=None, to_date=None, year=None, interval="Monthly"):
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        filters = {
            "docstatus": 1,
            "company": company
        }

        if year:
            filters["posting_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]
        elif from_date and to_date:
            filters["posting_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["posting_date"] = [">=", from_date]
        elif to_date:
            filters["posting_date"] = ["<=", to_date]

        invoices = frappe.get_all(
            "Sales Invoice",
            filters=filters,
            fields=["posting_date", "base_grand_total", "outstanding_amount", "conversion_rate"]
        )

        total_receivable = 0.0
        total_received = 0.0
        trend_data = {} 

        for inv in invoices:
            receivable_pending = flt(inv.outstanding_amount) * flt(inv.conversion_rate)
            
            # The amount already paid (Total Invoiced - Pending)
            received = flt(inv.base_grand_total) - receivable_pending

            # 2. UPDATE OVERALL TOTALS
            total_receivable += receivable_pending
            total_received += received

            if inv.posting_date:
                date_obj = getdate(inv.posting_date)
                year_str = date_obj.strftime("%Y")
                month = date_obj.month

                if interval == "Yearly":
                    group_key = year_str
                elif interval == "Half-Yearly":
                    h_val = "H1" if month <= 6 else "H2"
                    group_key = f"{year_str}-{h_val}"
                elif interval == "Quarterly":
                    q_val = f"Q{((month - 1) // 3) + 1}"
                    group_key = f"{year_str}-{q_val}"
                else:
                    # Default to Monthly
                    group_key = date_obj.strftime("%Y-%m")
                
                if group_key not in trend_data:
                    trend_data[group_key] = {"receivable": 0.0, "received": 0.0}
                
                trend_data[group_key]["receivable"] += receivable_pending
                trend_data[group_key]["received"] += received

        chart_data = {
            "totals": {
                "totalReceivable": total_receivable,
                "totalReceived": total_received
            },
            "trend": trend_data
        }

        return send_old_response(
            status="success",
            message="Sales chart data retrieved successfully.",
            data=chart_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Sales Chart API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving sales chart data: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def purchase_chart(from_date=None, to_date=None, year=None):
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        # 1. Build ORM Filters
        filters = {
            "docstatus": 1,
            "company": company
        }

        # Handle Date Range & Year logic for ORM
        if year:
            filters["posting_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]
        elif from_date and to_date:
            filters["posting_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["posting_date"] = [">=", from_date]
        elif to_date:
            filters["posting_date"] = ["<=", to_date]

        # 2. Fetch Data using ORM
        invoices = frappe.get_all(
            "Purchase Invoice",
            filters=filters,
            fields=["posting_date", "base_grand_total", "outstanding_amount"]
        )

        # 3. Process Data in Python Memory
        total_payable = 0.0
        total_paid = 0.0
        monthly_trend = {}

        for inv in invoices:
            payable = flt(inv.base_grand_total)
            paid = payable - flt(inv.outstanding_amount)

            # Aggregate Overall Totals
            total_payable += payable
            total_paid += paid

            # Group by Month for Trend
            if inv.posting_date:
                date_obj = getdate(inv.posting_date)
                month_key = date_obj.strftime("%Y-%m")
                
                if month_key not in monthly_trend:
                    monthly_trend[month_key] = {"payable": 0.0, "paid": 0.0}
                
                monthly_trend[month_key]["payable"] += payable
                monthly_trend[month_key]["paid"] += paid

        chart_data = {
            "totals": {
                "totalPayable": total_payable,
                "totalPaid": total_paid
            },
            "trend": monthly_trend
        }

        return send_old_response(
            status="success",
            message="Purchase chart data retrieved successfully.",
            data=chart_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Purchase Chart API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving purchase chart data: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def inventory_chart(from_date=None, to_date=None, year=None):
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        # Helper function to generate data grouped by month AND item
        def get_item_monthly_data(parent_doctype, child_doctype):
            parent = frappe.qb.DocType(parent_doctype)
            child = frappe.qb.DocType(child_doctype)
            item = frappe.qb.DocType("Item")

            # Join Child, Parent, and Item tables
            query = (
                frappe.qb.from_(child)
                .inner_join(parent).on(child.parent == parent.name)
                .inner_join(item).on(child.item_code == item.name)
                .select(
                    Extract('month', parent.posting_date).as_("month_num"),
                    child.item_code,
                    child.item_name,
                    Sum(child.qty).as_("total_qty"),
                    Sum(child.base_amount).as_("total_value")
                )
                .where(parent.docstatus == 1)
                .where(parent.company == company)
                .where(item.is_stock_item == 1) # Filter for stock items only
                .groupby(
                    Extract('month', parent.posting_date), 
                    child.item_code, 
                    child.item_name
                )
            )

            # Apply Date Filters
            if year:
                query = query.where(parent.posting_date >= f"{year}-01-01").where(parent.posting_date <= f"{year}-12-31")
            elif from_date and to_date:
                query = query.where(parent.posting_date >= from_date).where(parent.posting_date <= to_date)
            elif from_date:
                query = query.where(parent.posting_date >= from_date)
            elif to_date:
                query = query.where(parent.posting_date <= to_date)

            return query.run(as_dict=True)

        # ==========================================
        # 1. Fetch Monthly Data Grouped by Item
        # ==========================================
        selling_data = get_item_monthly_data("Sales Invoice", "Sales Invoice Item")
        buying_data = get_item_monthly_data("Purchase Invoice", "Purchase Invoice Item")

        # ==========================================
        # 2. Map Buying Data for Easy Lookup
        # ==========================================
        # Create a dictionary using (month_num, item_code) as the key
        buying_dict = {}
        for row in buying_data:
            key = (int(row.month_num), row.item_code)
            buying_dict[key] = {
                "buyQty": flt(row.total_qty),
                "buyValue": flt(row.total_value)
            }

        # ==========================================
        # 3. Find the Top Selling Item Per Month
        # ==========================================
        top_selling_per_month = {}
        
        for row in selling_data:
            month_idx = int(row.month_num) - 1 # Array index is 0-11
            if 0 <= month_idx < 12:
                current_qty = flt(row.total_qty)
                
                # If this month isn't tracked yet, OR if this item sold more than the currently tracked top item
                if month_idx not in top_selling_per_month or current_qty > top_selling_per_month[month_idx]["sellQty"]:
                    top_selling_per_month[month_idx] = {
                        "itemCode": row.item_code,
                        "itemName": row.item_name,
                        "sellQty": current_qty,
                        "sellValue": flt(row.total_value),
                        "month_num": int(row.month_num)
                    }

        # ==========================================
        # 4. Initialize and Populate 12 Months Array
        # ==========================================
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        chart_data = []

        for month_idx, month_name in enumerate(months):
            # Base object for the month
            base_data = {
                "month": month_name, 
                "itemCode": None,
                "itemName": "No Sales",
                "buyQty": 0.0,
                "buyValue": 0.0,
                "sellQty": 0.0,
                "sellValue": 0.0
            }

            # If there were sales this month, update with the top item
            if month_idx in top_selling_per_month:
                top_item = top_selling_per_month[month_idx]
                base_data["itemCode"] = top_item["itemCode"]
                base_data["itemName"] = top_item["itemName"]
                base_data["sellQty"] = top_item["sellQty"]
                base_data["sellValue"] = top_item["sellValue"]

                # Now, find if we bought THIS specific item in THIS specific month
                buy_key = (top_item["month_num"], top_item["itemCode"])
                if buy_key in buying_dict:
                    base_data["buyQty"] = buying_dict[buy_key]["buyQty"]
                    base_data["buyValue"] = buying_dict[buy_key]["buyValue"]

            chart_data.append(base_data)

        # ==========================================
        # 5. Return Final Data
        # ==========================================
        return send_old_response(
            status="success",
            message="Top inventory items per month retrieved successfully.",
            data=chart_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Inventory Chart API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving inventory chart data: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )