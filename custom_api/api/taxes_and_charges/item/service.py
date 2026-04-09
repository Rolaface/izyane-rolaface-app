from custom_api.api.taxes_and_charges.item.item_tax_utils import build_filters, map_item_tax_template, validate_item_tax_payload
import frappe

def upsert_item_tax_template(data):
    validate_item_tax_payload(data)

    name = data.get("name") 
    title = data.get("title")

    if not title:
        frappe.throw("Title is required")

    if name and frappe.db.exists("Item Tax Template", name):
        doc = frappe.get_doc("Item Tax Template", name)
        doc.taxes = []
    else:
        doc = frappe.new_doc("Item Tax Template")

    map_item_tax_template(doc, data)

    doc.save(ignore_permissions=True)

    return {
        "name": doc.name,
        "title": doc.title
    }

def get_item_tax_templates_service(args):

    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 10))

    limit_start = (page - 1) * page_size
    limit_page_length = page_size

    order_by = args.get("order_by", "modified desc")

    filters = build_filters(args)

    total_count = frappe.db.count("Item Tax Template", filters=filters)

    templates = frappe.get_all(
        "Item Tax Template",
        filters=filters,
        fields=["name", "title", "company", "disabled", "modified"],
        order_by=order_by,
        limit_start=limit_start,
        limit_page_length=limit_page_length
    )

    # Fetch child taxes
    for template in templates:
        template["taxes"] = frappe.get_all(
            "Item Tax Template Detail",
            filters={"parent": template["name"]},
            fields=["tax_type", "tax_rate"]
        )

    return {
        "templates": templates,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    }