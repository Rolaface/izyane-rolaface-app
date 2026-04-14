from custom_api.api.buying.purchase_order.utils import build_items
from custom_api.utils.party_utils import sync_terms
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