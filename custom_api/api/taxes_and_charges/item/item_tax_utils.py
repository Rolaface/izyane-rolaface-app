from custom_api.api.taxes_and_charges.utils import get_tax_account
import frappe

def validate_item_tax_payload(data):
    if not data:
        frappe.throw("Payload is required")

    if not data.get("taxes"):
        frappe.throw("At least one tax row is required")

def map_item_tax_template(doc, data):
    company_name = frappe.defaults.get_user_default("Company")
    company = frappe.get_doc("Company", company_name)

    doc.title = data.get("title")
    doc.company = company.name
    doc.disabled = data.get("disabled", 0)

    taxes = data.get("taxes", [])

    for row in taxes:
        doc.append("taxes", {
            "tax_type": row.get("tax_type") or get_tax_account(company.name, "Liability"),
            "tax_rate": row.get("tax_rate")
        })

def build_filters(args):
    filters = {}

    if args.get("company"):
        filters["company"] = args.get("company")

    if args.get("name"):
        filters["name"] = args.get("name")

    if args.get("disabled") is not None:
        filters["disabled"] = int(args.get("disabled"))

    if args.get("search"):
        filters["title"] = ["like", f"%{args.get('search')}%"]

    return filters