import frappe
from typing import Dict, Any

def validate_rfq_payload(data: Dict[str, Any], is_update=False):
    items = data.get("items")
    if items is not None:
        if not isinstance(items, list) or len(items) == 0:
            raise frappe.ValidationError("At least one item is required in the 'items' array.")

        for idx, item in enumerate(items):
            if not item.get("item_code"):
                raise frappe.ValidationError(f"Row {idx+1}: item_code is required.")
            if not item.get("qty") or float(item.get("qty")) <= 0:
                raise frappe.ValidationError(f"Row {idx+1}: qty must be greater than 0.")
            if not frappe.db.exists("Item", item.get("item_code")):
                raise frappe.ValidationError(f"Row {idx+1}: Item {item.get('item_code')} does not exist.")

    suppliers = data.get("suppliers")
    if suppliers is not None:
        if not isinstance(suppliers, list) or len(suppliers) == 0:
            raise frappe.ValidationError("At least one supplier is required in the 'suppliers' array.")
        
        for idx, supplier in enumerate(suppliers):
            if not supplier.get("supplier"):
                raise frappe.ValidationError(f"Supplier Row {idx+1}: supplier is required.")
            if not frappe.db.exists("Supplier", supplier.get("supplier")):
                raise frappe.ValidationError(f"Supplier Row {idx+1}: Supplier {supplier.get('supplier')} does not exist.")


def build_rfq_filters(args):
    frappe_filters = {}

    if not args:
        return frappe_filters

    if args.get("status"):
        frappe_filters["status"] = ["in", args["status"]]

    if args.get("from_date") and args.get("to_date"):
        frappe_filters["transaction_date"] = ["between", [args["from_date"], args["to_date"]]]

    if args.get("company"):
        frappe_filters["company"] = args["company"]

    return frappe_filters

def get_company_addresses(company):
    addresses = frappe.get_all(
        "Address",
        filters={
            "link_doctype": "Company",
            "link_name": company
        },
        fields=["name", "is_primary_address", "is_shipping_address"]
    )

    billing = None
    shipping = None

    for addr in addresses:
        if addr.is_primary_address and not billing:
            billing = addr.name
        if addr.is_shipping_address and not shipping:
            shipping = addr.name

    return billing, shipping