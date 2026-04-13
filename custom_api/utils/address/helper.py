import frappe

def build_address_filters(company=None, customer=None, supplier=None, address_type=None):

    filters = []

    if customer:
        filters.append(["Dynamic Link", "link_doctype", "=", "Customer"])
        filters.append(["Dynamic Link", "link_name", "=", customer])

    if supplier:
        filters.append(["Dynamic Link", "link_doctype", "=", "Supplier"])
        filters.append(["Dynamic Link", "link_name", "=", supplier])

    if company:
        company_name = frappe.defaults.get_user_default("Company")
        company = frappe.db.get_value("Company", company_name, "name")
        filters.append(["Dynamic Link", "link_doctype", "=", "Company"])
        filters.append(["Dynamic Link", "link_name", "=", company])

    if address_type:
        filters.append(["Address", "address_type", "=", address_type])

    return filters

def build_search_filters(search):

    if not search:
        return []

    return [
        ["Address", "name", "like", f"%{search}%"],
        ["Address", "address_title", "like", f"%{search}%"],
        ["Address", "city", "like", f"%{search}%"],
        ["Address", "country", "like", f"%{search}%"],
        ["Address", "address_line1", "like", f"%{search}%"],
        ["Address", "address_line2", "like", f"%{search}%"],
    ]

def map_address_response(addresses):

    data = []

    for addr in addresses:
        data.append({
            "id": addr.get("name"),
            "title": addr.get("address_title"),
            "type": addr.get("address_type"),
            "addressLine1": addr.get("address_line1"),
            "addressLine2": addr.get("address_line2"),
            "city": addr.get("city"),
            "state": addr.get("state"),
            "country": addr.get("country"),
            "pincode": addr.get("pincode"),
            "email": addr.get("email_id"),
            "phone": addr.get("phone"),
            "addressType": addr.get("address_type")
        })

    return data