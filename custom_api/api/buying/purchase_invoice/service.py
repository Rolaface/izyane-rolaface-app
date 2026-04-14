from custom_api.api.buying.purchase_order.utils import build_items
from custom_api.api.item.utils.item_utils import _get_tax
from custom_api.utils.party_utils import get_linked_terms, sync_terms
import frappe
from custom_api.api.buying.purchase_invoice.utils import (
    build_pi_filters,
    apply_pi_search,
    map_pi_list_response
)

def get_purchase_invoice_list(filters=None, page=1, page_size=10, search=""):

    filters = build_pi_filters(filters)

    limit_start = (page - 1) * page_size

    invoices = frappe.get_all(
        "Purchase Invoice",
        filters=filters,
        fields=[
            "name",
            "supplier",
            "posting_date",
            "due_date",
            "grand_total",
            "status",
            "currency",
            "total_taxes_and_charges",
            "outstanding_amount",
            "shipping_rule",
            "rounded_total",
            # "supplier_invoice_date"
        ],
        order_by="creation desc"
    )

    invoices = apply_pi_search(invoices, search)

    total = len(invoices)
    paginated_data = invoices[limit_start: limit_start + page_size]

    data = [map_pi_list_response(inv) for inv in paginated_data]

    total_pages = (total + page_size - 1) // page_size

    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    }

def create_purchase_invoice_service(data):

    if not data.get("supplierId"):
        frappe.throw("Supplier is required")

    company = frappe.defaults.get_user_default("Company")

    pi_doc = frappe.get_doc({
        "doctype": "Purchase Invoice",
    
        "company": company,
        "supplier": data.get("supplierId"),
        "contact_person": data.get("supplierContact"),
        "update_stock": data.get("updateStock", False),
        "posting_date": data.get("poDate"),
        "set_warehouse": data.get("warehouse"),
        "currency": data.get("currency", frappe.defaults.get_user_default("currency")),
        "tax_category": data.get("taxCategory"),
        "bill_no": data.get("spplrInvcNo"),
        "bill_date": data.get("spplrInvcDt"),
        "cost_center": data.get("costCenter"),
        "project": data.get("project"),
        "incoterm": data.get("incoterms"),
        "billing_address": data.get("billing_address"),
        "shipping_address": data.get("shipping_address"),
        "supplier_address": data.get("supplier_address"),
        "dispatch_address": data.get("dispatch_address"),

        "items": build_items(data.get("items"), data.get("supplierId")),
        "custom_invoice_metadata": [{"payment_mode": data.get("paymentType")}]
    })
    pi_doc.run_method("set_missing_values")
    pi_doc.run_method("calculate_taxes_and_totals")

    pi_doc.insert(ignore_permissions=True)

    terms = sync_terms(pi_doc, data.get("terms"), terms_type="buying")
    pi_doc.payment_terms_template = f"{pi_doc.name} Buying PT"   
    pi_doc.tc_name = terms
    pi_doc.terms = frappe.db.get_value("Terms and Conditions", terms, "terms") if terms else ""
    pi_doc.set("payment_schedule", [])

    pi_doc.run_method("set_missing_values")
    pi_doc.run_method("calculate_taxes_and_totals")
    pi_doc.save(ignore_permissions=True)

def get_purchase_invoice_by_id(pi_id):
    pi_doc = frappe.get_doc("Purchase Invoice", pi_id)
    po_items = []
    for item in pi_doc.items:

        item_meta = frappe.db.get_value(
            "Custom Item Details",
            {"parent": item.item_code},
            ["packing_unit", "packing_size"],
            as_dict=True
        )
        tax = _get_tax(item.item_code, pi_doc.tax_category)
        po_items.append({
            "itemCode": item.item_code,
            "itemName": item.item_name,
            "quantity": item.qty,
            "rate": item.rate,
            "warehouse": item.warehouse,
            "uom": item.uom,
            "batchNo": item.batch_no,
            "taxInfo": tax,
            "packingUnit": str(item_meta.get("packing_unit")) if item_meta else "",
            "packingSize": str(item_meta.get("packing_size")) if item_meta else ""
        })

    return {
        "piId": pi_doc.name,
        "supplierId": pi_doc.supplier,
        "supplierName": pi_doc.supplier_name,
        "poDate": str(pi_doc.posting_date) if pi_doc.posting_date else None,
        "currency": pi_doc.currency,
        "billingAddress": pi_doc.billing_address,
        "billingAddressDisplay": pi_doc.billing_address_display,
        "shippingAddress": pi_doc.shipping_address,
        "shippingAddressDisplay": pi_doc.shipping_address_display,
        "supplierAddress": pi_doc.supplier_address,
        "supplierAddressDisplay": pi_doc.address_display,
        "dispatchAddress": pi_doc.dispatch_address,
        "dispatchAddressDisplay": pi_doc.dispatch_address_display,
        "taxCategory": pi_doc.tax_category,
        "project": pi_doc.project,
        "costCenter": pi_doc.cost_center,
        "incoterms": pi_doc.incoterm,
        "terms": get_linked_terms(pi_doc.name, "buying"),
        "items": po_items,
        "totalTaxes": pi_doc.total_taxes_and_charges,
        "grandTotal": pi_doc.grand_total,
        "roundedTotal": pi_doc.rounded_total,
        "contactPerson": pi_doc.contact_person,
        "contactDisplay": pi_doc.contact_display,
        "paymentType": pi_doc.custom_invoice_metadata[0].payment_mode if pi_doc.custom_invoice_metadata else None
    }
