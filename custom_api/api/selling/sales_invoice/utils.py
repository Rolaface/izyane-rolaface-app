import frappe
from typing import Dict, Any

def validate_sales_invoice_payload(data: Dict[str, Any], is_update=False):
    if not is_update and not data.get("customerId"):
        raise frappe.ValidationError("customerId is required.")

    if not is_update and not frappe.db.exists("Customer", data.get("customerId")):
        raise frappe.ValidationError(f"Customer {data.get('customerId')} does not exist.")

    items = data.get("items")
    if items is not None:
        if not isinstance(items, list) or len(items) == 0:
            raise frappe.ValidationError("At least one item is required in the 'items' array.")
        
        for idx, item in enumerate(items):
            if not item.get("itemCode"):
                raise frappe.ValidationError(f"Row {idx+1}: itemCode is required.")
            if not item.get("quantity") or float(item.get("quantity")) <= 0:
                raise frappe.ValidationError(f"Row {idx+1}: quantity must be greater than 0.")
            if not frappe.db.exists("Item", item.get("itemCode")):
                raise frappe.ValidationError(f"Row {idx+1}: Item {item.get('itemCode')} does not exist.")

    posting_date = data.get("postingDate")
    due_date = data.get("dueDate")
    if posting_date and due_date:
        if due_date < posting_date:
            raise frappe.ValidationError("dueDate cannot be before postingDate.")
            
    terms = data.get("terms")
    if terms:
        phases = terms.get("selling", {}).get("payment", {}).get("phases", [])
        if phases:
            total_percentage = sum(float(phase.get("percentage", 0)) for phase in phases)
            if total_percentage != 100:
                raise frappe.ValidationError(f"Total percentage of payment phases must equal 100. Currently: {total_percentage}")