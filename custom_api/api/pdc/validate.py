from custom_api.api.pdc.constant import MANDATORY_FIELDS
import frappe
from frappe import _

def validate_mandatory_fields(data):
    missing = [field for field in MANDATORY_FIELDS if not data.get(field)]
    if missing:
        frappe.throw(_("The following fields are mandatory: {0}").format(", ".join(missing)))

def validate_unique_cheque_reference_number(cheque_reference_number, exclude_name=None):
    filters = {"cheque_reference_number": cheque_reference_number}
    if exclude_name:
        filters["name"] = ["!=", exclude_name]

    if frappe.db.exists("Custom Pdc Details", filters):
        frappe.throw(
            _("A PDC with Cheque Reference Number {0} already exists.").format(cheque_reference_number)
        )
