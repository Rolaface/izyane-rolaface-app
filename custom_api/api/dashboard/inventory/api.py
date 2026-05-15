import frappe
from custom_api.utils.response import send_old_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_top_3_items():
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        # Fetch the top 3 items based on total base_amount
        top_items = frappe.db.sql("""
            SELECT 
                i.item_code,
                i.item_name,
                SUM(i.qty) as total_qty,
                SUM(i.base_amount) as total_value
            FROM 
                `tabSales Invoice Item` i
            INNER JOIN 
                `tabSales Invoice` s ON s.name = i.parent
            WHERE 
                s.docstatus = 1 
                AND s.company = %s
            GROUP BY 
                i.item_code, i.item_name
            ORDER BY 
                total_value DESC
            LIMIT 3
        """, (company,), as_dict=True)

        return send_old_response(
            status="success",
            message="Top 3 items retrieved successfully.",
            data=top_items,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Top 3 Items API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving top 3 items: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_item_breakdown():
    try:
        company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")

        # Fetch grouped data directly from the database
        breakdown_data = frappe.db.sql("""
            SELECT 
                i.item_group as name,
                SUM(i.qty) as total_qty,
                SUM(i.base_amount) as total_value
            FROM 
                `tabSales Invoice Item` i
            INNER JOIN 
                `tabSales Invoice` s ON s.name = i.parent
            WHERE 
                s.docstatus = 1 
                AND s.company = %s
            GROUP BY 
                i.item_group
            ORDER BY 
                total_value DESC
        """, (company,), as_dict=True)

        return send_old_response(
            status="success",
            message="Item breakdown retrieved successfully.",
            data=breakdown_data,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Item Breakdown API Error")
        return send_old_response(
            status="error",
            message=f"Error retrieving item breakdown: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )