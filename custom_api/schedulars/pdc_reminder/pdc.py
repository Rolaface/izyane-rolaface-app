import frappe

def get_due_pdcs():
    today = frappe.utils.today()
    tomorrow = frappe.utils.add_days(today, 1)

    pdcs = frappe.get_all(
        "Custom Pdc Details",
        filters={
            "status": "Unused",
            "cheque_date": ["in", [today, tomorrow]],
        },
        fields=[
            "name",
            "document_type",
            "document_name",
            "cheque_reference_number",
            "cheque_date",
            "amount",
        ],
    )

    for pdc in pdcs:
        pdc["due_label"] = "Today" if str(pdc.cheque_date) == str(today) else "Tomorrow"

    return pdcs

def expire_overdue_pdcs():
    today = frappe.utils.today()

    overdue_names = frappe.get_all(
        "Custom Pdc Details",
        filters={
            "status": "Unused",
            "cheque_date": ["<", today],
        },
        pluck="name",
    )

    for name in overdue_names:
        frappe.db.set_value("Custom Pdc Details", name, "status", "Expired")

    return overdue_names
