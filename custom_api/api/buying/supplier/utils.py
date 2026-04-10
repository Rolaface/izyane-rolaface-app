import json
import re
import frappe
from typing import Dict, List, Any

def parse_api_payload() -> Dict[str, Any]:
    data = frappe.local.form_dict.copy()
    if hasattr(frappe.request, 'data') and frappe.request.data:
        try:
            raw_data = frappe.request.data
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode('utf-8')
            if raw_data.strip():
                parsed_json = json.loads(raw_data)
                if isinstance(parsed_json, dict):
                    data.update(parsed_json)
        except json.JSONDecodeError as e:
            raise frappe.ValidationError(f"Invalid JSON payload provided: {str(e)}")
    return data

def validate_supplier_payload(data: Dict[str, Any]):
    contacts = data.get("contacts", [])
    if contacts and isinstance(contacts, list):
        for contact in contacts:
            email = contact.get("email")
            if email:
                pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
                if not re.fullmatch(pattern, email):
                    raise frappe.ValidationError(f"Invalid email format in contacts: {email}")

    tpin = data.get("tpin")
    if tpin and not data.get("id") and frappe.db.exists("Supplier", {"tax_id": tpin}):
        raise frappe.exceptions.DuplicateEntryError(f"Supplier with TPIN {tpin} already exists.")

def unlink_and_disable_docs(child_doctype: str, parent_doctype: str, parent_name: str, disable: bool = True):
    linked_docs = frappe.get_all(
        "Dynamic Link",
        filters={"parenttype": child_doctype, "link_doctype": parent_doctype, "link_name": parent_name},
        pluck="parent"
    )
    for doc_name in set(linked_docs):
        doc = frappe.get_doc(child_doctype, doc_name)
        doc.links = [l for l in doc.links if not (l.link_doctype == parent_doctype and l.link_name == parent_name)]
        if disable and hasattr(doc, "disabled"):
            doc.disabled = 1
        doc.flags.ignore_links = True
        doc.save(ignore_permissions=True)
        if not doc.links:
            try:
                frappe.delete_doc(child_doctype, doc.name, ignore_permissions=True, force=True)
            except frappe.exceptions.LinkExistsError:
                pass

def sync_addresses(parent_doc, addresses_data: Any, is_update: bool = False):
    if not addresses_data:
        return
    if isinstance(addresses_data, str):
        try: addresses_data = json.loads(addresses_data)
        except json.JSONDecodeError: raise frappe.ValidationError("Invalid JSON format in 'addresses' array.")

    link_doctype = parent_doc.doctype
    link_name = parent_doc.name
    doc_title = parent_doc.name

    existing_links = frappe.get_all("Dynamic Link", filters={"parenttype": "Address", "link_doctype": link_doctype, "link_name": link_name}, pluck="parent")
    existing_addresses = set(existing_links)
    processed_addresses = set()
    primary_address = None

    for i, addr in enumerate(addresses_data):
        addr_id = addr.get("id") or addr.get("name")
        is_primary = 1 if addr.get("isPrimary") or i == 0 else 0

        if is_update and addr_id and frappe.db.exists("Address", addr_id):
            address = frappe.get_doc("Address", addr_id)
            address.address_title = doc_title
            address.address_type = addr.get("type", address.address_type)
            address.address_line1 = addr.get("line1", address.address_line1)
            address.address_line2 = addr.get("line2", address.address_line2)
            address.city = addr.get("city", address.city)
            address.state = addr.get("state", address.state)
            address.pincode = addr.get("postalCode", address.pincode)
            address.country = addr.get("country").title() if addr.get("country") else address.country
            address.is_primary_address = is_primary
            address.is_shipping_address = 1 if addr.get("isShipping") else 0
            link_exists = any(l.link_doctype == link_doctype and l.link_name == link_name for l in address.links)
            if not link_exists:
                address.append("links", {"link_doctype": link_doctype, "link_name": link_name})
            address.save(ignore_permissions=True)
            processed_addresses.add(address.name)
        else:
            address = frappe.get_doc({
                "doctype": "Address",
                "address_title": doc_title,
                "address_type": addr.get("type", "Billing"),
                "address_line1": addr.get("line1"),
                "address_line2": addr.get("line2"),
                "city": addr.get("city"),
                "state": addr.get("state"),
                "pincode": addr.get("postalCode"),
                "country": (addr.get("country") or frappe.defaults.get_global_default("country") or "India").title(),
                "email_id": getattr(parent_doc, "email_id", ""),
                "phone": getattr(parent_doc, "mobile_no", ""),
                "is_primary_address": is_primary,
                "is_shipping_address": 1 if addr.get("isShipping") else 0,
                "links": [{"link_doctype": link_doctype, "link_name": link_name}]
            }).insert(ignore_permissions=True)
            processed_addresses.add(address.name)
        if is_primary:
            primary_address = address.name

    if primary_address:
        parent_doc.db_set(f"{link_doctype.lower()}_primary_address", primary_address, update_modified=False)

    if is_update:
        addresses_to_remove = existing_addresses - processed_addresses
        for doc_name in addresses_to_remove:
            doc = frappe.get_doc("Address", doc_name)
            doc.links = [l for l in doc.links if not (l.link_doctype == link_doctype and l.link_name == link_name)]
            doc.disabled = 1
            doc.flags.ignore_links = True
            doc.save(ignore_permissions=True)
            if not doc.links:
                try: frappe.delete_doc("Address", doc.name, ignore_permissions=True, force=True)
                except frappe.exceptions.LinkExistsError: pass

def sync_contacts(parent_doc, contacts_data: Any, is_update: bool = False):
    if not contacts_data:
        return
    if isinstance(contacts_data, str):
        try: contacts_data = json.loads(contacts_data)
        except json.JSONDecodeError: raise frappe.ValidationError("Invalid JSON format in 'contacts' array.")

    link_doctype = parent_doc.doctype
    link_name = parent_doc.name

    existing_links = frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "link_doctype": link_doctype, "link_name": link_name}, pluck="parent")
    existing_contacts = set(existing_links)
    processed_contacts = set()

    primary_contact = None
    primary_email = ""
    primary_mobile = ""

    for i, contact_info in enumerate(contacts_data):
        contact_id = contact_info.get("id") or contact_info.get("name")
        first_name = contact_info.get("firstName") or contact_info.get("first_name", "")
        middle_name = contact_info.get("middleName") or contact_info.get("middle_name", "")
        last_name = contact_info.get("lastName") or contact_info.get("last_name", "")
        if not first_name and contact_info.get("name"):
            parts = str(contact_info.get("name")).strip().split()
            if len(parts) == 1: first_name = parts[0]
            elif len(parts) == 2: first_name, last_name = parts[0], parts[1]
            else: first_name, middle_name, last_name = parts[0], " ".join(parts[1:-1]), parts[-1]

        if not first_name:
            continue

        is_primary = 1 if contact_info.get("isPrimary") or i == 0 else 0
        email = contact_info.get("email")
        mobile = contact_info.get("mobile")
        phone = contact_info.get("phone")

        if is_update and contact_id and contact_id in existing_contacts:
            contact_doc = frappe.get_doc("Contact", contact_id)
            contact_doc.first_name = first_name
            contact_doc.middle_name = middle_name
            contact_doc.last_name = last_name
            contact_doc.salutation = contact_info.get("salutation", contact_doc.salutation)
            contact_doc.gender = contact_info.get("gender", contact_doc.gender)
            contact_doc.company_name = contact_info.get("companyName", contact_doc.company_name)
            contact_doc.designation = contact_info.get("designation", contact_doc.designation)
            contact_doc.department = contact_info.get("department", contact_doc.department)
            contact_doc.status = contact_info.get("status", contact_doc.status)
            contact_doc.is_primary_contact = is_primary
            contact_doc.is_billing_contact = 1 if contact_info.get("isBilling") or contact_info.get("is_billing_contact") else 0
            contact_doc.set("email_ids", [])
            contact_doc.set("phone_nos", [])
            if email: contact_doc.append("email_ids", {"email_id": email, "is_primary": 1})
            if mobile: contact_doc.append("phone_nos", {"phone": mobile, "is_primary_mobile_no": 1})
            if phone: contact_doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
            contact_doc.save(ignore_permissions=True)
            processed_contacts.add(contact_doc.name)
        else:
            contact_doc = frappe.get_doc({
                "doctype": "Contact",
                "first_name": first_name,
                "middle_name": middle_name,
                "last_name": last_name,
                "salutation": contact_info.get("salutation", ""),
                "gender": contact_info.get("gender", ""),
                "company_name": contact_info.get("companyName") or contact_info.get("company_name", ""),
                "designation": contact_info.get("designation", ""),
                "department": contact_info.get("department", ""),
                "status": contact_info.get("status", "Passive"),
                "is_primary_contact": is_primary,
                "is_billing_contact": 1 if contact_info.get("isBilling") or contact_info.get("is_billing_contact") else 0,
                "links": [{"link_doctype": link_doctype, "link_name": link_name}]
            })
            if email: contact_doc.append("email_ids", {"email_id": email, "is_primary": 1})
            if mobile: contact_doc.append("phone_nos", {"phone": mobile, "is_primary_mobile_no": 1})
            if phone: contact_doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1})
            contact_doc.insert(ignore_permissions=True)
            processed_contacts.add(contact_doc.name)

        if is_primary:
            primary_contact = contact_doc.name
            primary_email = email
            primary_mobile = mobile

    if primary_contact:
        updates = {}
        primary_field = f"{link_doctype.lower()}_primary_contact"
        if hasattr(parent_doc, primary_field) and getattr(parent_doc, primary_field) != primary_contact:
            updates[primary_field] = primary_contact
        if hasattr(parent_doc, "email_id") and primary_email:
            updates["email_id"] = primary_email
        if hasattr(parent_doc, "mobile_no") and primary_mobile:
            updates["mobile_no"] = primary_mobile
        if updates:
            parent_doc.db_set(updates, update_modified=False)

    if is_update:
        contacts_to_remove = existing_contacts - processed_contacts
        for doc_name in contacts_to_remove:
            doc = frappe.get_doc("Contact", doc_name)
            doc.links = [l for l in doc.links if not (l.link_doctype == link_doctype and l.link_name == link_name)]
            doc.flags.ignore_links = True
            doc.save(ignore_permissions=True)
            if not doc.links:
                try: frappe.delete_doc("Contact", doc.name, ignore_permissions=True, force=True)
                except frappe.exceptions.LinkExistsError: pass

def sync_payment_terms(parent_doc, payment_data: Dict, terms_type: str):
    if not payment_data or not isinstance(payment_data, dict):
        return
    phases = payment_data.get("phases")
    if not phases or not isinstance(phases, list):
        return

    doc_title = parent_doc.name
    template_name = f"{doc_title} {terms_type.capitalize()} PT"
    existing_terms = []

    if frappe.db.exists("Payment Terms Template", template_name):
        template = frappe.get_doc("Payment Terms Template", template_name)
        existing_terms = [t.payment_term for t in template.terms]
        template.terms = []
    else:
        template = frappe.get_doc({
            "doctype": "Payment Terms Template",
            "template_name": template_name
        })

    new_terms = []
    total_pct = 0.0

    for phase in phases:
        term_name = phase.get("name")
        pct = frappe.utils.flt(phase.get("percentage"))
        credit_days = frappe.utils.cint(phase.get("credit_days", 0))
        total_pct += pct

        if not term_name:
            continue

        new_terms.append(term_name)

        if not frappe.db.exists("Payment Term", term_name):
            frappe.get_doc({
                "doctype": "Payment Term",
                "payment_term_name": term_name,
                "description": phase.get("condition", ""),
                "invoice_portion": pct,
                "due_date_based_on": "Day(s) after invoice date",
                "credit_days": credit_days
            }).insert(ignore_permissions=True)
        else:
            pt = frappe.get_doc("Payment Term", term_name)
            pt.description = phase.get("condition", "")
            pt.invoice_portion = pct
            pt.credit_days = credit_days
            pt.save(ignore_permissions=True)

        template.append("terms", {
            "payment_term": term_name,
            "invoice_portion": pct,
            "credit_days": credit_days
        })

    if round(total_pct, 2) == 100.00:
        template.save(ignore_permissions=True)
        if hasattr(parent_doc, "payment_terms") and parent_doc.payment_terms != template.name:
            parent_doc.db_set("payment_terms", template.name, update_modified=False)
        removed_terms = set(existing_terms) - set(new_terms)
        for term in removed_terms:
            try: frappe.delete_doc("Payment Term", term, ignore_permissions=True, force=True)
            except frappe.exceptions.LinkExistsError: pass
    else:
        raise frappe.ValidationError(f"Payment phases must sum to exactly 100%. Current sum is {round(total_pct, 2)}%.")

def sync_terms(parent_doc, terms_data: Any, terms_type: str = "buying"):
    if not terms_data:
        return

    if isinstance(terms_data, str):
        try: terms_data = json.loads(terms_data)
        except json.JSONDecodeError: raise frappe.ValidationError("Invalid JSON format in 'terms' object.")

    buying_terms = terms_data.get(terms_type)
    if not buying_terms:
        return

    sync_payment_terms(parent_doc, buying_terms.get("payment", {}), terms_type)

    doc_title = parent_doc.name
    expected_tc_name = f"{doc_title} {terms_type.capitalize()} Terms"
    
    if frappe.db.exists("Terms and Conditions", {"title": expected_tc_name, 
                                                 "selling": 1 if terms_type == "selling" else 0,
                                                 "buying": 1 if terms_type == "buying" else 0}):
        tc = frappe.get_doc("Terms and Conditions", expected_tc_name)
        tc.terms = json.dumps(buying_terms)
        tc.selling = 1 if terms_type == "selling" else 0
        tc.buying = 1 if terms_type == "buying" else 0
        tc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Terms and Conditions", "title": expected_tc_name,
            "terms": json.dumps(buying_terms), "selling": 1 if terms_type == "selling" else 0, "buying": 1 if terms_type == "buying" else 0
        }).insert(ignore_permissions=True)

    return expected_tc_name

def get_linked_addresses(link_doctype: str, link_name: str) -> List[Dict]:
    addresses = frappe.get_all(
        "Address",
        filters={"link_doctype": link_doctype, "link_name": link_name},
        fields=[
            "name as id", "address_type as type", "address_line1 as line1", "address_line2 as line2",
            "city", "state", "pincode as postalCode", "country",
            "is_primary_address as isPrimary", "is_shipping_address as isShipping"
        ]
    )
    for addr in addresses:
        addr["isPrimary"] = bool(addr.get("isPrimary"))
        addr["isShipping"] = bool(addr.get("isShipping"))
    return addresses

def get_linked_contacts(link_doctype: str, link_name: str) -> List[Dict]:
    linked_contact_names = frappe.get_all(
        "Dynamic Link",
        filters={"parenttype": "Contact", "link_doctype": link_doctype, "link_name": link_name},
        pluck="parent"
    )
    if not linked_contact_names:
        return []

    contacts = frappe.get_all(
        "Contact",
        filters={"name": ("in", linked_contact_names)},
        fields=[
            "name as id", "first_name as firstName", "middle_name as middleName", "last_name as lastName", "full_name as fullName",
            "salutation", "gender", "company_name as companyName", "status",
            "email_id as email", "mobile_no as mobile", "phone", 
            "designation", "department",
            "is_primary_contact as isPrimary", "is_billing_contact as isBilling"
        ]
    )
    for c in contacts:
        c["isPrimary"] = bool(c.get("isPrimary"))
        c["isBilling"] = bool(c.get("isBilling"))
    return contacts

def get_linked_terms(title_name: str) -> Dict:
    expected_tc_name = f"{title_name} Terms"
    if frappe.db.exists("Terms and Conditions", expected_tc_name):
        tc_doc = frappe.db.get_value("Terms and Conditions", expected_tc_name, "terms")
        term_type = "buying" if "Buying" in title_name else "selling"
        if tc_doc:
            try: return {term_type: json.loads(tc_doc)}
            except Exception: return {term_type: tc_doc}
    return {}