import frappe
from custom_api.schedulars.pdc_reminder.pdc import get_due_pdcs_grouped_by_contact_email
from custom_api.schedulars.pdc_reminder.utils import send_pdc_reminder_email

def send_pdc_reminders():
    try:
        email_map = get_due_pdcs_grouped_by_contact_email()

        if not email_map:
            print("No PDC reminders to send.")
            return

        for contact_email, pdcs in email_map.items():
            send_pdc_reminder_email(contact_email, pdcs)

        print(f"Sent PDC reminders to {len(email_map)} recipient(s).")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "PDC Reminder Scheduler Error")
        print("Error --->>> ", e)
