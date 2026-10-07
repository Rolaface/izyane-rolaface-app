import frappe
from ....utils.party_utils import (
    sync_addresses,
    sync_contacts,
    sync_terms,
    get_linked_addresses,
    get_linked_contacts,
    get_linked_terms,
    unlink_and_disable_docs,
)
from .utils import validate_credit_limits

def get_default_company():
    return frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")

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
        "customer_group": data.get("customerGroup", None),
        "disabled": 0,
    }
    if data.get("naming_series"):
        doc_args["naming_series"] = data.get("naming_series")

    ext_details = {}
    if data.get("registration_no") is not None:
        ext_details["registration_no"] = data.get("registration_no")

    if data.get("principalId") is not None:
        ext_details["principal_id"] = data.get("principalId")

    if data.get("credit_limits") is not None:
        default_company = get_default_company()
        doc_args["credit_limits"] = []
        
        for cl in data.get("credit_limits"):
            company = cl.get("company") or default_company
            cl["company"] = company 
            
            doc_args["credit_limits"].append({
                "company": company,
                "credit_limit": cl.get("credit_limit"),
                "bypass_credit_limit_check": cl.get("bypass_credit_limit_check", 0)
            })
            
            if cl.get("strict_credit_limit") is not None:
                ext_details["strict_credit_limit"] = cl.get("strict_credit_limit")
            
        validate_credit_limits(data)

    customer = frappe.get_doc(doc_args).insert(ignore_permissions=True)

    if ext_details:
        customer.append("custom_extended_details", ext_details)

    customer.save(ignore_permissions=True)
    # Process links
    sync_addresses(customer, data.get("addresses"), is_update=False)
    sync_contacts(customer, data.get("contacts"), is_update=False)
    sync_terms(customer, data.get("terms"), terms_type="selling")

    return customer


def update_customer(customer_id, data):
    customer = frappe.get_doc("Customer", customer_id)

    field_map = {
        "name": "customer_name",
        "type": "customer_type",
        "currency": "default_currency",
        "customerTaxCategory": "tax_category",
        "customerGroup": "customer_group",
        "mobile": "mobile_no",
        "email": "email_id",
        "tpin": "tax_id",
    }
    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(customer, v, data.get(k))

    if data.get("status"):
        raw_status = data.get("status")
        status = str(raw_status).strip().lower()
        customer.disabled = 0 if status == "active" else 1

    strict_credit_limit_val = None
    if data.get("credit_limits") is not None:
        default_company = get_default_company()
        customer.set("credit_limits", [])
        
        for cl in data.get("credit_limits"):
            company = cl.get("company") or default_company
            cl["company"] = company
            
            customer.append("credit_limits", {
                "company": company,
                "credit_limit": cl.get("credit_limit"),
                "bypass_credit_limit_check": cl.get("bypass_credit_limit_check", 0)
            })

            if cl.get("strict_credit_limit") is not None:
                strict_credit_limit_val = cl.get("strict_credit_limit")
            
        validate_credit_limits(data)

    if "registration_no" in data or strict_credit_limit_val is not None or "principalId" in data:
        if not customer.custom_extended_details:
            customer.append("custom_extended_details", {})
        
        ext_row = customer.custom_extended_details[0]
        if "registration_no" in data:
            ext_row.registration_no = data.get("registration_no")
        if strict_credit_limit_val is not None:
            ext_row.strict_credit_limit = strict_credit_limit_val
        if "principalId" in data:
            ext_row.principal_id = data.get("principalId")

    customer.save(ignore_permissions=True)

    # Sync links.
    sync_contacts(customer, data.get("contacts"), is_update=True)
    sync_addresses(customer, data.get("addresses"), is_update=True)
    sync_terms(customer, data.get("terms"), terms_type="selling")

    return customer


def get_customer_by_id(customer_id):
    customer = frappe.get_doc("Customer", customer_id)

    registration_no = None
    strict_credit_limit = 0
    principal_id = None

    if customer.custom_extended_details:
        registration_no = customer.custom_extended_details[0].registration_no
        strict_credit_limit = customer.custom_extended_details[0].strict_credit_limit
        principal_id = customer.custom_extended_details[0].principal_id

    credit_limits = [
        {
            "company": cl.company,
            "credit_limit": cl.credit_limit,
            "bypass_credit_limit_check": cl.bypass_credit_limit_check,
            "strict_credit_limit": strict_credit_limit 
        }
        for cl in customer.get("credit_limits", [])
    ]

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
        "registration_no": registration_no,
        "status": "Active" if not customer.disabled else "Inactive",
        "credit_limits": credit_limits,
        "contacts": get_linked_contacts("Customer", customer_id),
        "addresses": get_linked_addresses("Customer", customer_id),
        "terms": get_linked_terms(customer_id, "selling"),
        "principalId": principal_id,

    }


def get_customers(page, page_size, search=None, status=None):
    start = (page - 1) * page_size

    filters = {}

    if status:
        status = str(status).strip().lower()

        if status == "active":
            filters["disabled"] = 0
        elif status in ["inactive", "disabled"]:
            filters["disabled"] = 1

    or_filters = None
    if search:
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["customer_name", "like", f"%{search}%"],
            ["customer_type", "like", f"%{search}%"],
            ["email_id", "like", f"%{search}%"],
            ["tax_category", "like", f"%{search}%"],
        ]

    total_customers = frappe.db.count("Customer", filters=filters)

    total_pages = (total_customers + page_size - 1) // page_size

    customers = frappe.get_all(
        "Customer",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name",
            "customer_name",
            "customer_type",
            "tax_id",
            "mobile_no",
            "email_id",
            "default_currency",
            "tax_category",
            "disabled",
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by="creation desc",
    )

    for c in customers:
        c["id"] = c.pop("name")
        c["name"] = c.pop("customer_name")
        c["tpin"] = c.pop("tax_id")
        c["type"] = c.pop("customer_type")
        c["mobile"] = c.pop("mobile_no")
        c["email"] = c.pop("email_id")
        c["currency"] = c.pop("default_currency")
        c["status"] = "Active" if not c.pop("disabled") else "Inactive"
        c["customerTaxCategory"] = c.pop("tax_category")
        c["contacts"] = get_linked_contacts("Customer", c["id"])

    return customers, total_customers, total_pages


def delete_customer(customer_id):
    frappe.db.set_value(
        "Customer",
        customer_id,
        {
            "customer_primary_contact": None,
            "customer_primary_address": None,
            "payment_terms": None,
        },
        update_modified=False,
    )

    unlink_and_disable_docs("Address", "Customer", customer_id, disable=True)
    unlink_and_disable_docs("Contact", "Customer", customer_id, disable=False)

    frappe.delete_doc("Customer", customer_id, ignore_permissions=True)

    for terms_type in ["Selling", "Buying"]:
        tc_name = f"{customer_id} {terms_type} Terms"
        pt_name = f"{customer_id} {terms_type} PT"

        if frappe.db.exists("Terms and Conditions", tc_name):
            frappe.delete_doc(
                "Terms and Conditions", tc_name, ignore_permissions=True, force=True
            )

        if frappe.db.exists("Payment Terms Template", pt_name):
            template_doc = frappe.get_doc("Payment Terms Template", pt_name)
            terms_to_delete = [t.payment_term for t in template_doc.terms]
            frappe.delete_doc(
                "Payment Terms Template", pt_name, ignore_permissions=True, force=True
            )
            for term in terms_to_delete:
                try:
                    frappe.delete_doc(
                        "Payment Term", term, ignore_permissions=True, force=True
                    )
                except frappe.exceptions.LinkExistsError:
                    pass


def update_customer_status(customer_id, status):
    is_disabled = 0 if status == "active" else 1
    customer = frappe.get_doc("Customer", customer_id)
    if customer.disabled != is_disabled:
        customer.disabled = is_disabled
        customer.save(ignore_permissions=True)
    return status.title()