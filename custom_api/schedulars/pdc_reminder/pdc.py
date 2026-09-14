import frappe

def get_due_pdcs_grouped_by_contact_email():
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

    email_map = {}

    for pdc in pdcs:
        pdc["due_label"] = "Today" if str(pdc.cheque_date) == str(today) else "Tomorrow"

        contact_email = None
        if pdc.document_type and pdc.document_name:
            contact_email = frappe.db.get_value(pdc.document_type, pdc.document_name, "contact_email")

        if not contact_email:
            continue

        if contact_email not in email_map:
            email_map[contact_email] = []
        email_map[contact_email].append(pdc)

    return email_map

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
