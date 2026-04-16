import frappe

def build_pi_filters(args):

    frappe_filters = {}

    if not args:
        return frappe_filters
    minOutstanding= args.get("minOutstanding")
    maxOutstanding = args.get("maxOutstanding")
    if args.get("supplier"):
        frappe_filters["supplier"] = args["supplier"]

    if args.get("status"):
        status_filter = args.getlist("status")
        frappe_filters["status"] = ["in", status_filter]

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
        "outstanding_amount": outstanding
    }

def apply_advances(po_no, pi_doc):

    # Fetch Payment Entry references linked to PO
    pe_references = frappe.get_all(
        "Payment Entry Reference",
        filters={
            "reference_doctype": "Purchase Order",
            "reference_name": po_no,
        },
        fields=["name", "parent", "allocated_amount", "exchange_rate"],
    )

    remaining_to_allocate = float(pi_doc.outstanding_amount or pi_doc.grand_total or 0)

    for ref in pe_references:
        if remaining_to_allocate <= 0:
            break

        available_advance = float(ref.get("allocated_amount") or 0)

        if available_advance <= 0:
            continue

        # Correct allocation logic
        allocate = min(remaining_to_allocate, available_advance)

        pi_doc.append("advances",{
            # "doctype": "Purchase Invoice Advance",
            "reference_type": "Payment Entry",
            "reference_name": ref["parent"],
            "advance_amount": available_advance,
            "allocated_amount": allocate,
            # "parentfield": "advances",
            # "parenttype": "Purchase Invoice",
            "reference_row": ref["name"],
            "ref_exchange_rate": ref["exchange_rate"],
            "remarks": f"Advance settled against LPO {po_no}",
        })

        remaining_to_allocate = round(remaining_to_allocate - allocate, 2)