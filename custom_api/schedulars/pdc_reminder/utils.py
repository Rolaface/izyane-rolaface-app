import frappe

PDC_REMINDER_TEMPLATE = "custom_api/templates/pdc_reminder.html"

def send_pdc_reminder_email(contact_email, pdcs):
    table_html = frappe.render_template(PDC_REMINDER_TEMPLATE, {"pdcs": pdcs})
    due_today = any(pdc.due_label == "Today" for pdc in pdcs)
    due_tomorrow = any(pdc.due_label == "Tomorrow" for pdc in pdcs)

    if due_today and due_tomorrow:
        subject = "Reminder: PDC(s) due today and tomorrow"
    elif due_today:
        subject = "Reminder: PDC(s) due today"
    else:
        subject = "Reminder: PDC(s) due tomorrow"

    message = f"""
        <p>Dear Sir/Madam,</p>
        <p>This is a reminder for the following Post Dated Cheque(s) (PDC) that need to be submitted:</p>
        {table_html}
        <p>Please ensure timely submission/processing.</p>
    """

    frappe.sendmail(
        recipients=[contact_email],
        subject=subject,
        content=message,
        raw_html=True,
    )
