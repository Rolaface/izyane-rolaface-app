import frappe
def get_warehouses(company):
    warehouses = frappe.db.get_all("Warehouse", filters={"company": company, "is_group": 0}, pluck="name")
    return warehouses

STATUS_MAP = {
    "Approved": {
        "action": "submit",
        "erp_status": "To Receive and Bill"
    },
    "Cancelled": {
        "action": "cancel",
        "erp_status": "Cancelled"
    },
    "Completed": {
        "action": None,
        "erp_status": "Completed"
    }
}