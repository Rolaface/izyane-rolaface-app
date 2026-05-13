import frappe
from frappe.utils import flt
from custom_api.utils.response import send_response # or send_old_response depending on your exact import

@frappe.whitelist(allow_guest=False, methods=["GET"])
def custom_employee_details(employee_id):
    if not employee_id:
        return send_response(
            status="error",
            message="Missing required parameter: employee_id",
            data=None,
            status_code=400,
            http_status=400,
        )

    try:
        employee_info = frappe.db.get_value(
            "Employee", 
            employee_id, 
            ["name", "employee_name", "department", "designation", "status", "company", "date_of_joining"], 
            as_dict=True
        )

        if not employee_info:
            return send_response(
                status="error",
                message=f"Employee with ID {employee_id} not found.",
                data=None,
                status_code=404,
                http_status=404,
            )

        leave_balances_data = frappe.db.sql("""
            SELECT 
                leave_type, 
                COALESCE(SUM(CASE WHEN is_carry_forward = 1 AND leaves > 0 THEN leaves ELSE 0 END), 0) AS opening_balance,
                COALESCE(SUM(CASE WHEN transaction_type = 'Leave Allocation' AND is_carry_forward = 0 AND leaves > 0 THEN leaves ELSE 0 END), 0) AS new_leaves_allocated,
                COALESCE(SUM(CASE WHEN transaction_type = 'Leave Application' AND leaves < 0 THEN ABS(leaves) ELSE 0 END), 0) AS leaves_taken,
                COALESCE(SUM(CASE WHEN is_expired = 1 AND leaves < 0 THEN ABS(leaves) ELSE 0 END), 0) AS leaves_expired,
                COALESCE(SUM(leaves), 0) AS balance
            FROM `tabLeave Ledger Entry`
            WHERE employee = %(employee)s
            GROUP BY leave_type
        """, {"employee": employee_id}, as_dict=True)

        recent_timesheets = frappe.db.get_all(
            "Timesheet",
            filters={"employee": employee_id, "docstatus": 1},
            fields=["name", "start_date", "end_date", "total_hours", "status"],
            order_by="start_date desc",
            limit=10,
        )

        total_hours_query = frappe.db.sql("""
            SELECT 
                COALESCE(SUM(total_hours), 0) AS total_logged_hours
            FROM `tabTimesheet`
            WHERE employee = %(employee)s
              AND docstatus = 1
        """, {"employee": employee_id}, as_dict=True)
        
        total_logged_hours = total_hours_query[0].total_logged_hours if total_hours_query else 0.0

        return send_response(
            status="success",
            message="Employee details retrieved successfully.",
            data={
                "employeeInfo": employee_info,
                "leaveBalances": leave_balances_data,
                "timesheetDetails": {
                    "totalLoggedHours": flt(total_logged_hours),
                    "recentTimesheets": recent_timesheets
                }
            },
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Employee Details API Error - {employee_id}")
        return send_response(
            status="error",
            message=f"Error retrieving employee details: {str(e)}",
            data=None,
            status_code=500,
            http_status=500,
        )