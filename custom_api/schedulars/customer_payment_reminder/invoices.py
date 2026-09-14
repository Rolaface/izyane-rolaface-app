import frappe

def get_overdue_invoices_grouped_by_customer():

    pdc_invoice_names = frappe.get_all(
        "Tag Link",
        filters={"document_type": "Sales Invoice", "tag": "PDC"},
        pluck="document_name",
    )

    filters = {
        "docstatus": 1,
        "status": ["in", ["Overdue", "Partly Paid", "unpaid"]],
    }
    if pdc_invoice_names:
        filters["name"] = ["not in", pdc_invoice_names]

    total_overdue_invoices = frappe.db.count(
        "Sales Invoice",
        filters={**filters, "status": ["in", ["Overdue"]]},
    )

    if total_overdue_invoices == 0:
        print("No overdue invoices found.")
        return {}

    invoices = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "due_date",
            "outstanding_amount",
            "contact_email",
            "posting_date",
            "status"
        ],
    )

    customer_map = {}

    for inv in invoices:
        customer = inv.customer

        if customer not in customer_map:
            customer_map[customer] = {
                "customer":          customer,
                "customer_name":     inv.customer_name,
                "contact_email":     inv.contact_email,
                "total_outstanding": 0.0,
                "invoices":          [],
            }

        customer_map[customer]["total_outstanding"] += float(inv.outstanding_amount or 0)
        customer_map[customer]["invoices"].append(inv)
    print(customer_map)
    return customer_map