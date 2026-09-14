from custom_api.api.pdc.constant import MANDATORY_FIELDS
import frappe

def validate_mandatory_fields(data):
    missing = [field for field in MANDATORY_FIELDS if not data.get(field)]
    if missing:
        frappe.throw(_("The following fields are mandatory: {0}").format(", ".join(missing)))
