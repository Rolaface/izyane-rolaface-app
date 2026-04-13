from custom_api.utils.address.helper import build_address_filters, build_search_filters, map_address_response
import frappe

def get_address_list_service(company=None, customer=None, supplier=None,
                                address_type=None, search=None
                            ):

    filters = build_address_filters(company, customer, supplier, address_type)
    or_filters = build_search_filters(search)

    addresses = frappe.get_all(
        "Address",
        filters=filters,
        or_filters=or_filters if search else None,
        fields=[
            "name",
            "address_title",
            "address_type",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "country",
            "pincode",
            "email_id",
            "phone",
            "address_type"
        ]
    )

    data = map_address_response(addresses)

    return data