import frappe
from custom_api.api.buying.purchase_invoice.utils import (
    build_pi_filters,
    apply_pi_search,
    map_pi_list_response
)

def get_purchase_invoice_list(filters=None, page=1, page_size=10, search=""):

    filters = build_pi_filters(filters)

    limit_start = (page - 1) * page_size

    invoices = frappe.get_all(
        "Purchase Invoice",
        filters=filters,
        fields=[
            "name",
            "supplier",
            "posting_date",
            "due_date",
            "grand_total",
            "status",
            "currency",
            "total_taxes_and_charges",
            "outstanding_amount",
            "shipping_rule",
            "rounded_total",
            # "supplier_invoice_date"
        ],
        order_by="creation desc"
    )

    invoices = apply_pi_search(invoices, search)

    total = len(invoices)
    paginated_data = invoices[limit_start: limit_start + page_size]

    data = [map_pi_list_response(inv) for inv in paginated_data]

    total_pages = (total + page_size - 1) // page_size

    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    }