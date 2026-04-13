import frappe
from custom_api.api.taxes_and_charges.sales.sales_tax_utils import build_filters, map_sales_tax_template, patch_sales_tax_template, validate_sales_tax_payload

def create_sales_tax_template_service(data):
    validate_sales_tax_payload(data)

    title = data.get("title")
    
    if not title:
        frappe.throw("Title is required to create a template")

    name = data.get("name") or title

    if frappe.db.exists("Sales Taxes and Charges Template", name):
        frappe.throw(f"Sales Tax Template '{name}' already exists. Use the update API instead.")

    doc = frappe.new_doc("Sales Taxes and Charges Template")
    
    if data.get("name"):
        doc.name = data.get("name")

    map_sales_tax_template(doc, data)

    doc.insert(ignore_permissions=True)

    return {
        "name": doc.name,
        "title": doc.title
    }

def update_sales_tax_template_service(template_name, data, is_patch=False):
    if not is_patch:
        validate_sales_tax_payload(data)

    if not template_name:
        frappe.throw("Query parameter 'name' is required to update/patch a template")

    if not frappe.db.exists("Sales Taxes and Charges Template", template_name):
        frappe.throw(f"Sales Tax Template '{template_name}' not found.", exc=frappe.DoesNotExistError)

    doc = frappe.get_doc("Sales Taxes and Charges Template", template_name)
    
    if is_patch:
        patch_sales_tax_template(doc, data)
    else:
        doc.taxes = [] 
        map_sales_tax_template(doc, data)

    doc.save(ignore_permissions=True)

    return {
        "name": doc.name,
        "title": doc.title
    }

def get_sales_tax_templates_service(args):
    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 10))

    limit_start = (page - 1) * page_size
    limit_page_length = page_size

    order_by = args.get("order_by", "modified desc")

    filters = build_filters(args)

    total_count = frappe.db.count("Sales Taxes and Charges Template", filters=filters)

    templates = frappe.get_all(
        "Sales Taxes and Charges Template",
        filters=filters,
        fields=["name", "title", "company", "disabled", "is_default", "modified"],
        order_by=order_by,
        limit_start=limit_start,
        limit_page_length=limit_page_length
    )

    for template in templates:
        template["taxes"] = frappe.get_all(
            "Sales Taxes and Charges",
            filters={"parent": template["name"]},
            fields=["name", "charge_type", "account_head", "rate", "tax_amount", "description"]
        )

    return {
        "templates": templates,
        "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total_count,
                "total_pages": max(1, (total_count + page_size - 1) // page_size),
                "has_next": page < ((total_count + page_size - 1) // page_size),
                "has_prev": page > 1
            }
    }

def update_sales_tax_status_service(data, name):
    disabled = data.get("disabled")

    if not name:
        frappe.throw("Sales Tax Template 'name' is required")

    if disabled is None:
        frappe.throw("'disabled' field is required (0 or 1)")

    if int(disabled) not in [0, 1]:
        frappe.throw("'disabled' must be 0 (Enable) or 1 (Disable)")

    if not frappe.db.exists("Sales Taxes and Charges Template", name):
        frappe.throw("Sales Tax Template not found")

    doc = frappe.get_doc("Sales Taxes and Charges Template", name)

    doc.disabled = int(disabled)

    doc.save(ignore_permissions=True)

    return {
        "name": doc.name,
        "disabled": doc.disabled
    }

def get_sales_tax_template_service(name):
    if not frappe.db.exists("Sales Taxes and Charges Template", name):
        frappe.throw(f"Sales Tax Template '{name}' not found", exc=frappe.DoesNotExistError)

    doc = frappe.get_doc("Sales Taxes and Charges Template", name)

    template_data = {
        "name": doc.name,
        "title": doc.title,
        "company": doc.company,
        "disabled": doc.disabled,
        "is_default": doc.is_default,
        "tax_category": doc.tax_category,
        "modified": doc.modified,
        "taxes": []
    }

    for row in doc.get("taxes"):
        template_data["taxes"].append({
            "name": row.name,
            "charge_type": row.charge_type,
            "account_head": row.account_head,
            "rate": row.rate,
            "tax_amount":row.tax_amount,
            "description": row.description
        })

    return template_data

def delete_sales_tax_template_service(name):
    if not frappe.db.exists("Sales Taxes and Charges Template", name):
        frappe.throw(f"Sales Tax Template '{name}' not found", exc=frappe.DoesNotExistError)

    frappe.delete_doc("Sales Taxes and Charges Template", name, ignore_permissions=True)

    return {
        "name": name,
        "deleted": True
    }