import frappe
from ....utils.party_utils import (
    sync_addresses, sync_contacts, sync_terms,
    get_linked_addresses, get_linked_contacts, get_linked_terms,
    unlink_and_disable_docs
)

def create_customer(data):
    doc_args = {
        "doctype": "Customer",
        "customer_name": data.get("name"),
        "customer_type": data.get("type"),
        "mobile_no": data.get("mobile"),
        "email_id": data.get("email"),
        "tax_id": data.get("tpin"),
        "tax_category": data.get("customerTaxCategory"),
        "default_currency": data.get("currency"),
        "customer_group": data.get("customerGroup", "All Customer Groups"),
        "disabled": 0
    }
    if data.get("naming_series"):
        doc_args["naming_series"] = data.get("naming_series")

    # 1. Insert and save the core document first
    customer = frappe.get_doc(doc_args).insert(ignore_permissions=True)

    # 2. Process links. The sync functions will use db_set to update primary fields. 
    # Because customer is already in the DB, this works perfectly without a second save().
    sync_addresses(customer, data.get("addresses"), is_update=False)
    sync_contacts(customer, data.get("contacts"), is_update=False)
    sync_terms(customer, data.get("terms"), terms_type="selling")
    
    return customer

def update_customer(customer_id, data):
    # 1. Load the document
    customer = frappe.get_doc("Customer", customer_id)

    # 2. Map fields to the memory object
    field_map = {
        "name": "customer_name", 
        "type": "customer_type", 
        "currency": "default_currency",
        "customerTaxCategory": "tax_category", 
        "customerGroup": "customer_group",
        "mobile": "mobile_no",
        "email": "email_id",
        "tpin": "tax_id"
    }
    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(customer, v, data.get(k))

    if data.get("status"):
        raw_status = data.get("status")
        status = str(raw_status).strip().lower()
        customer.disabled = 0 if status == "active" else 1

    # 3. SAVE THE MAIN DOCUMENT FIRST
    # This prevents the Timestamp Mismatch because we secure our core updates 
    # before Frappe's background link updates can mess with the DB timestamps.
    customer.save(ignore_permissions=True)

    # 4. Sync links. Any parent updates triggered here happen via direct DB queries (db_set),
    # meaning we don't need a final save and avoid the mismatch crash entirely.
    sync_contacts(customer, data.get("contacts"), is_update=True)
    sync_addresses(customer, data.get("addresses"), is_update=True)
    sync_terms(customer, data.get("terms"), terms_type="selling")

    return customer

def get_customer_by_id(customer_id):
    customer = frappe.get_doc("Customer", customer_id)

    return {
        "id": customer.name,
        "name": customer.customer_name,
        "type": customer.customer_type,
        "tpin": customer.tax_id,
        "currency": customer.default_currency,
        "mobile": customer.mobile_no,
        "email": customer.email_id,
        "customerGroup": customer.customer_group,
        "customerTaxCategory": customer.tax_category,
        "status": "Active" if not customer.disabled else "Inactive",
        "contacts": get_linked_contacts("Customer", customer_id),
        "addresses": get_linked_addresses("Customer", customer_id),
        "terms": get_linked_terms(customer_id, "selling")
    }

def get_customers(page, page_size, search):
    start = (page - 1) * page_size
    total_customers = frappe.db.count("Customer")
    total_pages = (total_customers + page_size - 1) // page_size
    if search:
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["customer_name", "like", f"%{search}%"],
            ["status", "like", f"%{search}%"],
            ["customer_type", "like", f"%{search}%"],
            ["email_id", "like", f"%{search}"],
            ["tax_category", "like", f"%{search}"],
        ]
    customers = frappe.get_all(
        "Customer",
        or_filters=or_filters if search else None,
        fields=["name", "customer_name", "customer_type", "tax_id", "mobile_no", "email_id", "default_currency", "tax_category", "disabled"],
        limit_start=start, limit_page_length=page_size, order_by="creation desc"
    )

    for c in customers:
        c["id"] = c.pop("name")
        c["name"] = c.pop("customer_name")
        c["tpin"] = c.pop("tax_id")
        c["type"] = c.pop("customer_type")
        c["mobile"] = c.pop("mobile_no")
        c["email"] = c.pop("email_id")
        c["currency"] = c.pop("default_currency")
        c["status"] = "Active" if not c.pop("disabled") else "Disabled"
        c["customerTaxCategory"] = c.pop("tax_category")
        c["contacts"] = get_linked_contacts("Customer", c["id"])

    return customers, total_customers, total_pages
def delete_customer(customer_id):
    frappe.db.set_value("Customer", customer_id, {
        "customer_primary_contact": None, 
        "customer_primary_address": None,
        "payment_terms": None
    }, update_modified=False)

    unlink_and_disable_docs("Address", "Customer", customer_id, disable=True)
    unlink_and_disable_docs("Contact", "Customer", customer_id, disable=False)

    frappe.delete_doc("Customer", customer_id, ignore_permissions=True)

    for terms_type in ["Selling", "Buying"]:
        tc_name = f"{customer_id} {terms_type} Terms"
        pt_name = f"{customer_id} {terms_type} PT"

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

def update_customer_status(customer_id, status):
    is_disabled = 0 if status == "active" else 1
    customer = frappe.get_doc("Customer", customer_id)
    if customer.disabled != is_disabled:
        customer.disabled = is_disabled
        customer.save(ignore_permissions=True)
    return status.title()
