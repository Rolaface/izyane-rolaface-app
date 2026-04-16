import frappe

def before_validate(doc, method):

    default_cost_center = frappe.db.get_value("Company", doc.company, "cost_center")
    
    if doc.taxes:
        for tax in doc.taxes:
            if not tax.cost_center:
                tax.cost_center = default_cost_center