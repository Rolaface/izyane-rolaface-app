import frappe
import re
from frappe.utils import validate_email_address
from custom_api.utils.response import send_response

def _parse_and_validate_emails(email_input, field_name):
    if not email_input:
        return []
        
    emails = [e.strip() for e in re.split(r'[,;]', str(email_input)) if e.strip()]

    valid_emails = []
    for email in emails:
        if not validate_email_address(email, throw=False):
            raise frappe.ValidationError(f"Invalid email address found in '{field_name}': {email}")
        valid_emails.append(email)
        
    return valid_emails


@frappe.whitelist(allow_guest=False, methods=["POST"])
def send_email():
    try:
        data = frappe.form_dict
        
        try:
            recipients = _parse_and_validate_emails(data.get("recipients"), "recipients")
            cc = _parse_and_validate_emails(data.get("cc"), "cc")
            bcc = _parse_and_validate_emails(data.get("bcc"), "bcc")
        except frappe.ValidationError as e:
            return send_response(
                status="fail", message=str(e), status_code=400, http_status=400
            )

        if not recipients:
            return send_response(
                status="fail",
                message="At least one valid recipient is required in 'recipients'.",
                status_code=400,
                http_status=400,
            )

        subject = data.get("subject")
        message = data.get("message")
        
        if not subject or not message:
            return send_response(
                status="fail",
                message="'subject' and 'message' are required fields.",
                status_code=400,
                http_status=400,
            )

        processed_attachments = []
        
        if hasattr(frappe.request, "files") and frappe.request.files:
            for file_key in frappe.request.files.keys():
                for file_storage in frappe.request.files.getlist(file_key):
                    file_content = file_storage.read()
                    file_name = file_storage.filename
                    
                    if file_name and file_content:
                        processed_attachments.append({
                            "fname": file_name,
                            "fcontent": file_content
                        })

        frappe.sendmail(
            recipients=recipients,
            cc=cc,
            bcc=bcc,
            subject=subject,
            message=message,
            attachments=processed_attachments,
            delayed=True, 
        )

        return send_response(
            status="success",
            message="Email queued for sending successfully.",
            status_code=202,
            http_status=202,
        )

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Custom Send Email API Error")
        return send_response(
            status="error",
            message=f"Internal Server Error: {str(e)}",
            status_code=500,
            http_status=500,
        )