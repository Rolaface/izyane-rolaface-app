import frappe
from ....utils.party_utils import (
    sync_addresses, sync_contacts, sync_terms,
    get_linked_addresses, get_linked_contacts, get_linked_terms,
    unlink_and_disable_docs
)


def create_supplier(data):
    doc_args = {
        "doctype": "Supplier",
        "supplier_name": data.get("name"),
        "supplier_type": data.get("type"),
        "supplier_group": data.get("supplierGroup", "All Supplier Groups"),
        "tax_id": data.get("tpin"),
        "tax_category": data.get("supplierTaxCategory"),
        "default_currency": data.get("currency"),
        "disabled": 0 if data.get("status", "Active") == "Active" else 1
    }
    if data.get("naming_series"):
        doc_args["naming_series"] = data.get("naming_series")

    supplier = frappe.get_doc(doc_args).insert(ignore_permissions=True)

    sync_addresses(supplier, data.get("addresses"), is_update=False)
    sync_contacts(supplier, data.get("contacts"), is_update=False)
    sync_terms(supplier, data.get("terms"), terms_type="buying")
    supplier.save(ignore_permissions=True)

    return supplier

def update_supplier(supplier_id, data):
    supplier = frappe.get_doc("Supplier", supplier_id)

    field_map = {
        "name": "supplier_name", "type": "supplier_type", "currency": "default_currency",
        "supplierTaxCategory": "tax_category", "supplierGroup": "supplier_group"
    }
    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(supplier, v, data.get(k))

    if data.get("status"):
        raw_status = data.get("status")
        status = str(raw_status).strip().lower()
        supplier.disabled = 0 if status == "active" else 1

    supplier.save(ignore_permissions=True)
    
    sync_contacts(supplier, data.get("contacts"), is_update=True)
    sync_addresses(supplier, data.get("addresses"), is_update=True)
    sync_terms(supplier, data.get("terms"), terms_type="buying")
    supplier.save(ignore_permissions=True)

    return supplier

def get_supplier_by_id(supplier_id):
    supplier = frappe.get_doc("Supplier", supplier_id)

    return {
        "id": supplier.name,
        "name": supplier.supplier_name,
        "type": supplier.supplier_type,
        "tpin": supplier.tax_id,
        "currency": supplier.default_currency,
        "supplierGroup": supplier.supplier_group,
        "supplierTaxCategory": supplier.tax_category,
        "status": "Active" if not supplier.disabled else "Inactive",
        "createdAt":supplier.creation,
        "contacts": get_linked_contacts("Supplier", supplier_id),
        "addresses": get_linked_addresses("Supplier", supplier_id),
        "terms": get_linked_terms(supplier_id, "Buying")
    }

def get_suppliers(page, page_size):
    start = (page - 1) * page_size
    total_suppliers = frappe.db.count("Supplier")
    total_pages = (total_suppliers + page_size - 1) // page_size

    suppliers = frappe.get_all(
        "Supplier",
        fields=["name", "supplier_name", "supplier_type", "supplier_group", "tax_id", "default_currency", "tax_category", "disabled"],
        limit_start=start, limit_page_length=page_size, order_by="creation desc"
    )

    for s in suppliers:
        s["id"] = s.pop("name")
        s["name"] = s.pop("supplier_name")
        s["tpin"] = s.pop("tax_id")
        s["type"] = s.pop("supplier_type")
        s["supplierGroup"] = s.pop("supplier_group")
        s["currency"] = s.pop("default_currency")
        s["status"] = "Active" if not s.pop("disabled") else "Inactive"
        s["supplierTaxCategory"] = s.pop("tax_category")
        s["contacts"] = get_linked_contacts("Supplier", s["id"])

    return suppliers, total_suppliers, total_pages

def delete_supplier(supplier_id):
    frappe.db.set_value("Supplier", supplier_id, {
        "supplier_primary_contact": None, 
        "supplier_primary_address": None,
        "payment_terms": None
    }, update_modified=False)

    unlink_and_disable_docs("Address", "Supplier", supplier_id, disable=True)
    unlink_and_disable_docs("Contact", "Supplier", supplier_id, disable=False)

    frappe.delete_doc("Supplier", supplier_id, ignore_permissions=True)

    for terms_type in ["Selling", "Buying"]:
        tc_name = f"{supplier_id} {terms_type} Terms"
        pt_name = f"{supplier_id} {terms_type} PT"

        if frappe.db.exists("Terms and Conditions", tc_name):
            frappe.delete_doc("Terms and Conditions", tc_name, ignore_permissions=True, force=True)

        if frappe.db.exists("Payment Terms Template", pt_name):
            template_doc = frappe.get_doc("Payment Terms Template", pt_name)
            terms_to_delete = [t.payment_term for t in template_doc.terms]
            frappe.delete_doc("Payment Terms Template", pt_name, ignore_permissions=True, force=True)
            for term in terms_to_delete:
                try:
                    frappe.delete_doc("Payment Term", term, ignore_permissions=True, force=True)
                except frappe.exceptions.LinkExistsError:
                    pass

def update_supplier_status(supplier_id, status):
    is_disabled = 0 if status == "active" else 1
    supplier = frappe.get_doc("Supplier", supplier_id)
    if supplier.disabled != is_disabled:
        supplier.disabled = is_disabled
        supplier.save(ignore_permissions=True)
    return status.title()