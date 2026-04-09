import frappe

def validate_tax_category(data):
    if not data:
        frappe.throw("Payload is required")

    if not data.get("title"):
        frappe.throw("Title is required")

def map_tax_category(doc, data):
    doc.title = data.get("title") or doc.title
    doc.disabled = data.get("disabled", 0)

def build_tax_category_filters(args):
    filters = {}

    if args.get("name"):
        filters["name"] = args.get("name")

    if args.get("disabled") is not None:
        filters["disabled"] = int(args.get("disabled"))

    if args.get("search"):
        filters["title"] = ["like", f"%{args.get('search')}%"]

    return filters