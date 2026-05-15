import frappe
from frappe.utils import flt, getdate, nowdate, date_diff
from custom_api.utils.response import send_old_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_procurement_summary():
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        # Suppliers (Global, not strictly tied to company in ERPNext)
        total_suppliers = frappe.db.count("Supplier")
        active_suppliers = frappe.db.count("Supplier", {"disabled": 0})
        inactive_suppliers = frappe.db.count("Supplier", {"disabled": 1})

        # Purchase Orders & Invoices (Submitted status = 1)
        total_pos = frappe.db.count("Purchase Order", {"docstatus": 1, "company": company})
        total_pis = frappe.db.count("Purchase Invoice", {"docstatus": 1, "company": company})

        summary_data = {
            "totalSuppliers": total_suppliers,
            "activeSuppliers": active_suppliers,
            "inactiveSuppliers": inactive_suppliers,
            "totalPurchaseOrders": total_pos,
            "totalPurchaseInvoices": total_pis
        }

        return send_old_response(
            status="success",
            message="Procurement summary retrieved successfully.",
            data=summary_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Procurement Summary API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving procurement summary: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_procurement_details(year=None):
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")
        today = getdate(nowdate())

        po_filters = {"docstatus": 1, "company": company}
        pi_filters = {"docstatus": 1, "company": company}

        # Apply Year Filter if provided
        if year:
            po_filters["transaction_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]
            pi_filters["posting_date"] = ["between", [f"{year}-01-01", f"{year}-12-31"]]

        # ==========================================
        # 1. PURCHASE ORDERS DATA
        # ==========================================
        purchase_orders = frappe.get_all(
            "Purchase Order",
            filters=po_filters,
            fields=["transaction_date", "base_grand_total", "status", "supplier", "supplier_name"]
        )

        po_amount_by_month = {m: 0.0 for m in range(1, 13)}
        po_status_distribution = {}
        supplier_totals = {}

        for po in purchase_orders:
            amount = flt(po.base_grand_total)
            
            # 1a. PO Amount by Month
            if po.transaction_date:
                month_idx = getdate(po.transaction_date).month
                po_amount_by_month[month_idx] += amount

            # 1b. PO Status Distribution (Count of statuses)
            status = po.status or "Unknown"
            po_status_distribution[status] = po_status_distribution.get(status, 0) + 1

            # 1c. Top Suppliers
            sup_name = po.supplier_name or po.supplier
            supplier_totals[sup_name] = supplier_totals.get(sup_name, 0.0) + amount

        # ==========================================
        # 2. PURCHASE INVOICES DATA
        # ==========================================
        purchase_invoices = frappe.get_all(
            "Purchase Invoice",
            filters=pi_filters,
            fields=["posting_date", "due_date", "base_grand_total", "outstanding_amount", "conversion_rate"]
        )

        pi_amount_by_month = {m: 0.0 for m in range(1, 13)}
        total_invoiced = 0.0
        total_unpaid = 0.0
        aging = {"0-30 Days": 0.0, "31-60 Days": 0.0, "61-90 Days": 0.0, "90+ Days": 0.0}

        for pi in purchase_invoices:
            inv_total = flt(pi.base_grand_total)
            
            # Handle multi-currency outstanding amounts cleanly
            conversion_rate = flt(pi.conversion_rate) or 1.0
            unpaid = flt(pi.outstanding_amount) * conversion_rate
            
            total_invoiced += inv_total
            total_unpaid += unpaid

            # 2a. Invoice Amount by Month
            if pi.posting_date:
                month_idx = getdate(pi.posting_date).month
                pi_amount_by_month[month_idx] += inv_total

            # 2b. Invoice Aging (Only for overdue/unpaid invoices)
            if unpaid > 0 and pi.due_date:
                due_date = getdate(pi.due_date)
                if today > due_date:
                    days_overdue = date_diff(today, due_date)
                    if days_overdue <= 30:
                        aging["0-30 Days"] += unpaid
                    elif days_overdue <= 60:
                        aging["31-60 Days"] += unpaid
                    elif days_overdue <= 90:
                        aging["61-90 Days"] += unpaid
                    else:
                        aging["90+ Days"] += unpaid

        # ==========================================
        # 3. FORMAT DATA FOR FRONTEND
        # ==========================================
        months_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        chart_data = {
            "purchaseOrders": {
                "monthlyTrend": [{"month": months_labels[i-1], "amount": po_amount_by_month[i]} for i in range(1, 13)],
                "statusDistribution": [{"name": k, "value": v} for k, v in po_status_distribution.items()],
                # Sort descending and grab top 10
                "topSuppliers": [{"name": k, "amount": v} for k, v in sorted(supplier_totals.items(), key=lambda item: item[1], reverse=True)[:10]]
            },
            "purchaseInvoices": {
                "monthlyTrend": [{"month": months_labels[i-1], "amount": pi_amount_by_month[i]} for i in range(1, 13)],
                "paidVsUnpaid": [
                    {"name": "Paid", "amount": total_invoiced - total_unpaid},
                    {"name": "Unpaid", "amount": total_unpaid}
                ],
                "aging": [{"name": k, "amount": v} for k, v in aging.items()]
            }
        }

        return send_old_response(
            status="success",
            message="Procurement details retrieved successfully.",
            data=chart_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Procurement Details API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving procurement details: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )