import frappe

def update_journal_entry_status(jv_id, action):
    jv = frappe.get_doc("Journal Entry", jv_id)
    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

    if not frappe.has_permission("Journal Entry", "write", jv):
        raise frappe.PermissionError("No permission to modify this entry")

    if action == "approved":
        if jv.docstatus == 1:
            raise frappe.ValidationError("Entry is already approved.")
        if jv.docstatus == 2:
            raise frappe.ValidationError("Cannot approve a cancelled entry. Please amend it first.")
        jv.submit()
        return {"id": jv.name, "status": status_map.get(jv.docstatus), "docstatus": jv.docstatus}

    elif action == "cancelled":
        if jv.docstatus == 2:
            raise frappe.ValidationError("Entry is already cancelled.")
        if jv.docstatus == 0:
            raise frappe.ValidationError("Cannot cancel a Draft entry. Submit it first.")
        jv.cancel()
        return {"id": jv.name, "status": status_map.get(jv.docstatus), "docstatus": jv.docstatus}

    elif action == "amend":
        if jv.docstatus == 0:
            raise frappe.ValidationError("Entry is already in Draft state.")
        if jv.docstatus == 1:
            raise frappe.ValidationError("Cannot amend an approved entry. Cancel it first.")
        amended_doc = frappe.copy_doc(jv)
        amended_doc.amended_from = jv.name
        amended_doc.docstatus = 0
        amended_doc.insert()
        return {"id": amended_doc.name, "status": status_map.get(amended_doc.docstatus), "docstatus": amended_doc.docstatus}

    else:
        raise frappe.ValidationError("Invalid action. Allowed: approved, cancelled, amend")