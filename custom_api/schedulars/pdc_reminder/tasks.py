import frappe
from custom_api.schedulars.pdc_reminder.pdc import get_due_pdcs, expire_overdue_pdcs
from custom_api.schedulars.pdc_reminder.utils import send_pdc_reminder_email

def send_pdc_reminders():
    try:
        pdcs = get_due_pdcs()

        if not pdcs:
            print("No PDC reminders to send.")
        else:
            company = frappe.defaults.get_user_default("Company")
            company_email = frappe.db.get_value("Company", company, "email") if company else None

            if not company_email:
                print("Company email is not configured; skipped PDC reminder.")
            else:
                send_pdc_reminder_email(company_email, pdcs)
                print(f"Sent PDC reminder to {company_email} for {len(pdcs)} PDC(s).")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "PDC Reminder Scheduler Error")
        print("Error --->>> ", e)

    try:
        expired_pdcs = expire_overdue_pdcs()

        if expired_pdcs:
            print(f"Marked {len(expired_pdcs)} PDC(s) as Expired.")
        else:
            print("No PDCs to expire.")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "PDC Expiry Scheduler Error")
        print("Error --->>> ", e)
