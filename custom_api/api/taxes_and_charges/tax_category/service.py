from custom_api.api.taxes_and_charges.tax_category.tax_category_utils import build_tax_category_filters, map_tax_category, validate_tax_category
import frappe

def create_tax_category_service(data):
    
    validate_tax_category(data)

    title = data.get("title")

    existing = frappe.db.get_value("Tax Category", {"title": title}, "name")
    if existing:
        frappe.throw(f"Tax Category already exists: {existing}")

    doc = frappe.new_doc("Tax Category")

    return _save_tax_category(doc, data)


def update_tax_category_service(data):
    
    name = data.get("name")
    if not name:
        frappe.throw("Tax Category 'name' is required for update")

    if not frappe.db.exists("Tax Category", name):
        frappe.throw("Tax Category not found")

    doc = frappe.get_doc("Tax Category", name)

    return _save_tax_category(doc, data)


def _save_tax_category(doc, data):
    map_tax_category(doc, data)

    doc.save(ignore_permissions=True)

    return {
        "name": doc.name,
        "title": doc.title,
        "disabled": doc.disabled
    }

def get_tax_categories_service(args):

    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 10))

    limit_start = (page - 1) * page_size
    limit_page_length = page_size

    order_by = args.get("order_by", "modified desc")

    filters = build_tax_category_filters(args)

    total_count = frappe.db.count("Tax Category", filters=filters)

    categories = frappe.get_all(
        "Tax Category",
        filters=filters,
        fields=["name", "title", "disabled"],
        order_by=order_by,
        limit_start=limit_start,
        limit_page_length=limit_page_length
    )

    return {
        "data": categories,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    }