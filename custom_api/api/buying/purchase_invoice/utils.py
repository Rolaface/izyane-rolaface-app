from custom_api.api.selling.sales_invoice.utils import update_item_tax_doc
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
        mapped_statuses = []
        status = args.get("status")
        status_filters = status.split(",") if isinstance(status, str) else status
        for status_filter in status_filters:
            mapped_statuses.append(status_filter)
        frappe_filters["status"] = ["in", mapped_statuses]

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

def sync_taxes(invoice):
    installed_apps = frappe.get_installed_apps()
    if "zra_smart_invoice" in installed_apps:
        invoice.set("taxes", [])

        default_cc = ( 
                        invoice.cost_center or 
                        frappe.get_cached_value("Company", invoice.company, "cost_center")
                      )

        existing_heads = set()

        for item in invoice.get("items", []):

            if not item.item_tax_template:
                continue

            item_tax_doc = frappe.get_cached_doc(
                "Item Tax Template",
                item.item_tax_template,
            )
            item_tax_doc = update_item_tax_doc(item_tax_doc)
            previous_row = None
            for item_tax in item_tax_doc.taxes:

                tax_head = item_tax.tax_type

                if tax_head in existing_heads:
                    continue

                if previous_row is None:
                    charge_type = "On Net Total"
                    row_id = None
                else:
                    charge_type = "On Previous Row Total"
                    row_id = previous_row.idx
                
                new_row = invoice.append( "taxes",{
                                    "doctype": "Sales Taxes and Charges",
                                    "charge_type": charge_type,
                                    "account_head": tax_head,
                                    "description": tax_head,
                                    "cost_center": default_cc,
                                    "rate": item_tax.tax_rate,
                                    "tax_amount": 0,
                                    "row_id": row_id,
                                })
                previous_row = new_row
                existing_heads.add(tax_head)