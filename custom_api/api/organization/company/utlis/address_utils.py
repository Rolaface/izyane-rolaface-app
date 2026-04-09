import frappe

def get_company_addresses(company_name):
    address_links = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Company",
            "link_name": company_name,
            "parenttype": "Address"
        },
        fields=["parent"]
    )

    addresses = []

    for link in address_links:
        address = frappe.get_doc("Address", link.parent)

        addresses.append({
            "addressType": address.address_type,
            "isPrimary": address.is_primary_address,
            "addressLine1": address.address_line1,
            "addressLine2": address.address_line2,
            "city": address.city,
            "district": address.county,
            "province": address.state,
            "postalCode": address.pincode,
            "country": address.country,
        })

    return addresses

def create_or_update_company_address(company, address_data):
    if not address_data:
        return

    # Find existing company address
    existing_address = frappe.db.get_value(
        "Dynamic Link",
        {
            "link_doctype": "Company",
            "link_name": company.name,
            "parenttype": "Address"
        },
        "parent"
    )

    if existing_address:
        address = frappe.get_doc("Address", existing_address)
    else:
        address = frappe.new_doc("Address")
        address.address_title = company.company_name
        address.address_type = address_data.get("addressType", "Office")  # Default to "Office" if not provided, in future will have muliple address support

    # Map fields
    address.address_line1 = address_data.get("addressLine1")
    address.address_line2 = address_data.get("addressLine2")
    address.city = address_data.get("city")
    address.state = address_data.get("province")
    address.country = address_data.get("country")
    address.pincode = address_data.get("postalCode")

    address.county = address_data.get("district")

    address.is_your_company_address = 1
    address.is_primary_address = 1

    # Link handling
    if not address.get("links"):
        address.set("links", [])

    # Avoid duplicate links
    if not any(
        d.link_doctype == "Company" and d.link_name == company.name
        for d in address.links
    ):
        address.append("links", {
            "link_doctype": "Company",
            "link_name": company.name
        })

    address.save(ignore_permissions=True)