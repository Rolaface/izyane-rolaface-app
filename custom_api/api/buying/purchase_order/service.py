from custom_api.api.buying.purchase_order.utils import build_items
from custom_api.api.item.utils.item_utils import _get_tax
from custom_api.helper import STATUS_MAP
import frappe
from custom_api.utils.party_utils import get_linked_terms, sync_terms

def create_po_service(data):

    if not data.get("supplierId"):
        frappe.throw("Supplier is required")

    company = frappe.defaults.get_user_default("Company")

    po_doc = frappe.get_doc({
        "doctype": "Purchase Order",
        "supplier": data.get("supplierId"),
        "company": company,

        "transaction_date": data.get("transaction_date"),

        "schedule_date": data.get("schedule_date"),
        "set_warehouse": data.get("set_warehouse"),

        "currency": data.get("currency", "INR"),

        "items": build_items(data.get("items"), data.get("supplierId")),
        "billing_address": data.get("billing_address"),
        "shipping_address": data.get("shipping_address"),
        "supplier_address": data.get("supplier_address"),
        "dispatch_address": data.get("dispatch_address"),

        "tax_category": data.get("taxCategory"),
        "project": data.get("project"),
        "cost_center": data.get("costCenter"),
        "incoterm": data.get("incoterms"),
        "contact_person": data.get("contactPerson"),
    })
    
    po_doc.run_method("set_missing_values")
    po_doc.run_method("calculate_taxes_and_totals")
    po_doc.insert(ignore_permissions=True)

    terms = sync_terms(po_doc, data.get("terms"), terms_type="buying")
    po_doc.payment_terms_template = f"{po_doc.name} Buying PT"   
    po_doc.tc_name = terms
    po_doc.terms = frappe.db.get_value("Terms and Conditions", terms, "terms") if terms else ""
    po_doc.set("payment_schedule", [])

    po_doc.run_method("set_missing_values")
    po_doc.run_method("calculate_taxes_and_totals")
    po_doc.save(ignore_permissions=True)

def update_po_service(po_id, data):

    if not po_id:
        frappe.throw("PO ID is required")

    po_doc = frappe.get_doc("Purchase Order", po_id)

    # -------------------------
    # Basic Fields
    # -------------------------
    po_doc.supplier = data.get("supplierId")
    po_doc.transaction_date = data.get("transaction_date", po_doc.transaction_date)

    po_doc.schedule_date = data.get("schedule_date")
    po_doc.set_warehouse = data.get("set_warehouse")

    po_doc.currency = data.get("currency", "INR")

    po_doc.billing_address = data.get("billing_address")
    po_doc.shipping_address = data.get("shipping_address")
    po_doc.supplier_address = data.get("supplier_address")
    po_doc.dispatch_address = data.get("dispatch_address")

    po_doc.tax_category = data.get("taxCategory")
    po_doc.project = data.get("project")
    po_doc.cost_center = data.get("costCenter")
    po_doc.incoterms = data.get("incoterms")


    po_doc.set("items", [])

    for item in build_items(data.get("items"), data.get("supplierId")):
        po_doc.append("items", item)

    po_doc.set("taxes", [])

    terms = sync_terms(po_doc, data.get("terms"), terms_type="buying")

    po_doc.payment_terms_template = f"{po_doc.name} Buying PT"
    po_doc.tc_name = terms

    # po_doc.run_method("set_tc_name")

    # po_doc.set("payment_schedule", [])

    po_doc.run_method("set_missing_values")
    po_doc.run_method("calculate_taxes_and_totals")

    po_doc.save(ignore_permissions=True)

    return po_doc

def get_po_list(filters=None, page=1, page_size=10, search=""):

    filters = filters or {}

    limit_start = (page - 1) * page_size

    or_filters = []
    if search:
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["supplier", "like", f"%{search}%"],
            ["status", "like", f"%{search}%"],
            ["transaction_date", "like", f"%{search}%"],
            ["schedule_date", "like", f"%{search}"],
            ["grand_total", "like", f"%{search}"],
        ]

    pos = frappe.get_all(
        "Purchase Order",
        filters=filters,
        or_filters=or_filters if search else None,
        fields=["name", "supplier", "transaction_date", "schedule_date", "grand_total", "status", "shipping_rule"],
        limit_start=limit_start,
        limit_page_length=page_size,
        order_by="creation desc"
    )

    for po in pos:
        po["poId"] = po.pop("name")
        po["supplierName"] = po.pop("supplier")
        po["poDate"] = str(po.pop("transaction_date")) if po.get("transaction_date") else None
        po["deliveryDate"] = str(po.pop("schedule_date")) if po.get("schedule_date") else None
        po["grandTotal"] = po.pop("grand_total")
        po["shippingRule"] = po.pop("shipping_rule")
        erp_status = po["status"]
        for api_status, config in STATUS_MAP.items():
            if erp_status == config["erp_status"]:
                po["status"] = api_status
                break

    total_po = frappe.db.count("Purchase Order", filters)
    total_pages = (total_po + page_size - 1) // page_size

    return {
            "data": pos,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_po,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }
        
def get_po_by_id(po_id):
    
    po_doc = frappe.get_doc("Purchase Order", po_id)

    po_items = []
    for item in po_doc.items:

        item_meta = frappe.db.get_value(
            "Custom Item Details",
            {"parent": item.item_code},
            ["packing_unit", "packing_size"],
            as_dict=True
        )
        tax = _get_tax(item.item_code, po_doc.tax_category)
        po_items.append({
            "itemCode": item.item_code,
            "itemName": item.item_name,
            "quantity": item.qty,
            "rate": item.rate,
            "requiredBy": str(item.schedule_date) if item.schedule_date else None,
            "warehouse": item.warehouse,
            "uom": item.uom,
            # "itemTaxTemplate": item.item_tax_template,
            "taxInfo": tax,
            "packingUnit": str(item_meta.get("packing_unit")) if item_meta else "",
            "packingSize": str(item_meta.get("packing_size")) if item_meta else ""
        })

    return {
        "poId": po_doc.name,
        "supplierId": po_doc.supplier,
        "supplierName": po_doc.supplier_name,
        "poDate": str(po_doc.transaction_date) if po_doc.transaction_date else None,
        "deliveryDate": str(po_doc.schedule_date) if po_doc.schedule_date else None,
        "currency": po_doc.currency,
        "billingAddress": po_doc.billing_address,
        "billingAddressDisplay": po_doc.billing_address_display,
        "shippingAddress": po_doc.shipping_address,
        "shippingAddressDisplay": po_doc.shipping_address_display,
        "supplierAddress": po_doc.supplier_address,
        "supplierAddressDisplay": po_doc.address_display,
        "dispatchAddress": po_doc.dispatch_address,
        "dispatchAddressDisplay": po_doc.dispatch_address_display,
        "taxCategory": po_doc.tax_category,
        "project": po_doc.project,
        "costCenter": po_doc.cost_center,
        "incoterms": po_doc.incoterm,
        "terms": get_linked_terms(po_doc.name, "buying"),
        "items": po_items,
        "totalTaxes": po_doc.total_taxes_and_charges,
        "grandTotal": po_doc.grand_total,
        "roundedTotal": po_doc.rounded_total,
        "contactPerson": po_doc.contact_person,
        "contactDisplay": po_doc.contact_display
    }