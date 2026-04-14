def build_pi_filters(args):

    frappe_filters = {}

    if not args:
        return frappe_filters
    minOutstanding= args.get("minOutstanding")
    maxOutstanding = args.get("maxOutstanding")
    if args.get("supplier"):
        frappe_filters["supplier"] = args["supplier"]

    if args.get("status"):
        frappe_filters["status"] = ["in", args["status"]]

    if args.get("from_date") and args.get("to_date"):
        frappe_filters["posting_date"] = ["between", [args["from_date"], args["to_date"]]]

    if args.get("company"):
        frappe_filters["company"] = args["company"]

    if minOutstanding and maxOutstanding:
        frappe_filters["outstanding_amount"] = ["between", [float(minOutstanding), float(maxOutstanding)]]
    elif minOutstanding:
        frappe_filters["outstanding_amount"] = [">=", float(minOutstanding)]
    elif maxOutstanding:
        frappe_filters["outstanding_amount"] = ["<=", float(maxOutstanding)]

    return frappe_filters

def apply_pi_search(invoices, search):

    if not search:
        return invoices

    search = search.lower()

    return [
        inv for inv in invoices
        if search in (inv.get("name") or "").lower()
        or search in (inv.get("supplier") or "").lower()
        or search in (inv.get("status") or "").lower()
        or search in str(inv.get("posting_date") or "").lower()
        or search in str(inv.get("due_date") or "").lower()
        or search in str(inv.get("grand_total") or "").lower()
    ]

def map_pi_list_response(inv):
    base_total = inv.get("grand_total", 0)
    tax = inv.get("total_taxes_and_charges", 0) or 0
    outstanding = inv.get("outstanding_amount") or 0
    rounded_total = inv.get("rounded_total") or 0
    return {
        "pId": inv.get("name"),
        "supplierName": inv.get("supplier"),
        "poDate": str(inv.get("posting_date")) if inv.get("posting_date") else None,
        "deliveryDate": str(inv.get("due_date")) if inv.get("due_date") else None,
        "grandTotal": base_total - tax,
        "paidAmount": (rounded_total or 0) - outstanding,
        "shippingRule": inv.get("shipping_rule"),
        "grandTotalWithTax": base_total,
        # "spplrInvcDt": inv.get("supplier_invoice_date"),
        "currency": inv.get("currency"),
        "status": inv.get("status"),
        "roundedTotal": rounded_total,
    }