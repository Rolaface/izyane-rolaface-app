import frappe
from .utils import build_rfq_filters, get_company_addresses
from frappe.utils import flt, cint
from frappe.contacts.doctype.address.address import get_address_display
import json

def create_rfq(data):
    rfq = frappe.new_doc("Request for Quotation")
    company = data.get("company") or frappe.defaults.get_user_default("Company")

    billing_address, shipping_address = get_company_addresses(company)
    terms_dict = data.get("terms")
    terms_text = json.dumps(terms_dict, indent=2) if terms_dict else None

    rfq.update({
        "transaction_date": data.get("transaction_date"),
        "schedule_date": data.get("schedule_date"),
        "company": company,
        "message_for_supplier": data.get("message_for_supplier"),
        "terms": terms_text,
        "billing_address": data.get("billing_address") or billing_address,
        "shipping_address": data.get("shipping_address") or shipping_address,
    })

    if rfq.billing_address:
        try:
            addr_doc = frappe.get_doc("Address", rfq.billing_address)
            rfq.billing_address_display = get_address_display(addr_doc.as_dict())
        except frappe.DoesNotExistError:
            frappe.throw(f"Invalid Billing Address: {rfq.billing_address}")

    if rfq.shipping_address:
        try:
            addr_doc = frappe.get_doc("Address", rfq.shipping_address)
            rfq.shipping_address_display = get_address_display(addr_doc.as_dict())
        except frappe.DoesNotExistError:
            frappe.throw(f"Invalid Shipping Address: {rfq.shipping_address}")

    for item in data.get("items", []):
        rfq.append("items", {
            "item_code": item.get("item_code"),
            "qty": item.get("qty"),
            "uom": item.get("uom"),
            "conversion_factor": item.get("conversion_factor", 1),
            "schedule_date": item.get("schedule_date", rfq.schedule_date),
            "warehouse": item.get("warehouse"),
            "description": item.get("description")
        })

    for supplier in data.get("suppliers", []):
        rfq.append("suppliers", {
            "supplier": supplier.get("supplier"),
            "contact": supplier.get("contact"),
            "email_id": supplier.get("email_id"),
            "send_email": supplier.get("send_email", 0)
        })

    rfq.insert(ignore_permissions=True)
    return rfq


def update_rfq(rfq_id, data):
    rfq = frappe.get_doc("Request for Quotation", rfq_id)

    if rfq.docstatus == 1:
        raise frappe.ValidationError("Cannot edit a submitted RFQ. Cancel it first.")
    
    fields_to_update = [
        "transaction_date", "schedule_date", "company", 
        "message_for_supplier"
    ]

    for field in fields_to_update:
        if field in data:
            setattr(rfq, field, data.get(field))

    if "terms" in data:
        terms_data = data.get("terms")
        rfq.terms = json.dumps(terms_data, indent=2) if isinstance(terms_data, dict) else terms_data

    if "billing_address" in data:
        rfq.billing_address = data.get("billing_address")
    if "shipping_address" in data:
        rfq.shipping_address = data.get("shipping_address")

    if not rfq.billing_address or not rfq.shipping_address:
        default_billing, default_shipping = get_company_addresses(rfq.company)
        if not rfq.billing_address:
            rfq.billing_address = default_billing
        if not rfq.shipping_address:
            rfq.shipping_address = default_shipping

    if rfq.billing_address:
        try:
            addr_doc = frappe.get_doc("Address", rfq.billing_address)
            rfq.billing_address_display = get_address_display(addr_doc.as_dict())
        except frappe.DoesNotExistError:
            frappe.throw(f"Invalid Billing Address: {rfq.billing_address}")
    else:
        rfq.billing_address_display = None

    if rfq.shipping_address:
        try:
            addr_doc = frappe.get_doc("Address", rfq.shipping_address)
            rfq.shipping_address_display = get_address_display(addr_doc.as_dict())
        except frappe.DoesNotExistError:
            frappe.throw(f"Invalid Shipping Address: {rfq.shipping_address}")
    else:
        rfq.shipping_address_display = None

    if "items" in data:
        rfq.set("items", [])
        for item in data.get("items"):
            rfq.append("items", {
                "item_code": item.get("item_code"),
                "qty": item.get("qty"),
                "uom": item.get("uom"),
                "conversion_factor": item.get("conversion_factor", 1),
                "schedule_date": item.get("schedule_date", rfq.schedule_date),
                "warehouse": item.get("warehouse", item.get("warehouse")),
                "description": item.get("description")
            })

    if "suppliers" in data:
        rfq.set("suppliers", [])
        for supplier in data.get("suppliers"):
            rfq.append("suppliers", {
                "supplier": supplier.get("supplier"),
                "contact": supplier.get("contact"),
                "email_id": supplier.get("email_id"),
                "send_email": supplier.get("send_email", 0)
            })

    rfq.save(ignore_permissions=True)
    return rfq


def get_rfq_by_id(rfq_id):
    rfq = frappe.get_doc("Request for Quotation", rfq_id)

    data = {
        "name": rfq.name,
        "transaction_date": rfq.transaction_date,
        "schedule_date": rfq.schedule_date,
        "company": rfq.company,
        "message_for_supplier": rfq.message_for_supplier,
        "status": rfq.status,
        "docstatus": rfq.docstatus,
        "billing_address": rfq.billing_address,
        "billing_address_display": rfq.billing_address_display,
        "shipping_address": rfq.shipping_address,
        "shipping_address_display": rfq.shipping_address_display,
        "terms": rfq.terms,
        "items": [],
        "suppliers": []
    }

    for item in rfq.items:
        data["items"].append({
            "item_code": item.item_code,
            # "item_name": item.item_name,
            "description": item.description,
            "uom": item.uom,
            "qty": item.qty,
            "conversion_factor": item.conversion_factor,
            "schedule_date": item.schedule_date,
            "warehouse": item.warehouse
        })

    for supplier in rfq.suppliers:
        data["suppliers"].append({
            "supplier": supplier.supplier,
            "supplier_name": supplier.supplier_name,
            "contact": supplier.contact,
            "email_id": supplier.email_id,
            "send_email": supplier.send_email,
            "quote_status": supplier.quote_status
        })

    return data


def get_rfqs(filters=None, page=1, page_size=20, search=None, sort_by="creation", sort_order="desc"):
    filters = filters or {}

    allowed_filters = {
        key: filters.get(key)
        for key in ["company", "status", "from_date", "to_date"]
        if filters.get(key) is not None
    }

    frappe_filters = build_rfq_filters(allowed_filters)

    or_filters = []
    if search:
        search = str(search).strip()
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["status", "like", f"%{search}%"],
            ["company", "like", f"%{search}%"],
        ]

    start = (page - 1) * page_size
    
    order_by_string = f"{sort_by} {sort_order}"

    rfqs = frappe.get_all(
        "Request for Quotation",
        filters=frappe_filters,
        or_filters=or_filters if search else None,
        fields=[
            "name",
            "transaction_date",
            "company",
            "status",
            "docstatus"
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by=order_by_string,
    )

    total_rfqs = len(
        frappe.get_all(
            "Request for Quotation",
            filters=frappe_filters,
            or_filters=or_filters if search else None,
            pluck="name",
        )
    )

    total_pages = (total_rfqs + page_size - 1) // page_size

    return rfqs, total_rfqs, total_pages


def delete_rfq(rfq_id):
    rfq = frappe.get_doc("Request for Quotation", rfq_id)
    if rfq.docstatus == 1:
        raise frappe.ValidationError(
            "Cannot delete a submitted RFQ. Cancel it first."
        )

    frappe.delete_doc("Request for Quotation", rfq_id, ignore_permissions=True)


def update_rfq_status(rfq_id, action):
    rfq = frappe.get_doc("Request for Quotation", rfq_id)

    if not frappe.has_permission("Request for Quotation", "write", rfq):
        raise frappe.PermissionError("No permission to modify this RFQ")

    if action == "submitted":
        if rfq.docstatus == 1:
            raise frappe.ValidationError("RFQ is already submitted.")
        if rfq.docstatus == 2:
            raise frappe.ValidationError(
                "Cannot submit a cancelled RFQ. Please amend it first."
            )

        rfq.submit()

        return {"name": rfq.name, "status": rfq.status, "docstatus": rfq.docstatus}

    elif action == "cancelled":
        if rfq.docstatus == 2:
            raise frappe.ValidationError("RFQ is already cancelled.")
        if rfq.docstatus == 0:
            raise frappe.ValidationError("Cannot cancel a Draft RFQ. Submit it first.")

        rfq.cancel()

        return {"name": rfq.name, "status": rfq.status, "docstatus": rfq.docstatus}

    elif action == "amend":
        if rfq.docstatus == 0:
            raise frappe.ValidationError("RFQ is already in Draft state.")
        if rfq.docstatus == 1:
            raise frappe.ValidationError("Cannot amend a submitted RFQ. Cancel it first.")

        amended_doc = frappe.copy_doc(rfq)
        amended_doc.amended_from = rfq.name
        amended_doc.docstatus = 0
        amended_doc.insert()

        return {"name": amended_doc.name, "status": amended_doc.status, "docstatus": amended_doc.docstatus}