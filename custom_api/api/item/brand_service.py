import frappe

def get_or_create_brand(brand_name: str):

    if not brand_name:
        return None

    # Check if brand exists
    existing_brand = frappe.db.exists("Brand", {"brand": brand_name})

    if existing_brand:
        return existing_brand

    # Create new brand
    brand_doc = frappe.get_doc({
        "doctype": "Brand",
        "brand": brand_name
    })

    brand_doc.insert(ignore_permissions=True)

    return brand_doc.name