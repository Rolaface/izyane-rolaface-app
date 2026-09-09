import frappe
from frappe import _

VALID_PURPOSES = ("Stock Reconciliation", "Opening Stock")

@frappe.whitelist()
def create_stock_correction(posting_date, items, warehouse=None, posting_time=None, purpose="Stock Reconciliation", expense_account=None):
    if isinstance(items, str):
        items = frappe.parse_json(items)

    if not items:
        frappe.throw(_("Items list is required"))

    if purpose not in VALID_PURPOSES:
        frappe.throw(_("Purpose must be one of: {0}").format(", ".join(VALID_PURPOSES)))

    if not frappe.db.get_single_value("Stock Settings", "use_serial_batch_fields"):
        frappe.db.set_single_value("Stock Settings", "use_serial_batch_fields", 1)
        frappe.db.commit()

    company = frappe.defaults.get_global_default("company")
    if not company:
        frappe.throw(_("No default company set in Global Defaults"))

    company_abbr = frappe.db.get_value("Company", company, "abbr")

    doc = frappe.new_doc("Stock Reconciliation")
    doc.company = company
    doc.purpose = purpose
    doc.posting_date = posting_date
    
    if posting_time:
        doc.set_posting_time = 1
        doc.posting_time = posting_time

    if purpose == "Opening Stock":
        if not expense_account:
            temp_account = f"Temporary Opening - {company_abbr}"
            if frappe.db.exists("Account", temp_account):
                expense_account = temp_account
            else:
                frappe.throw(_("Please specify an Asset/Liability 'expense_account' in your payload (e.g., 'Temporary Opening - {0}').").format(company_abbr))
    
    if expense_account:
        doc.expense_account = expense_account

    for row in items:
        item_code = row.get("item_code")
        row_warehouse = row.get("warehouse") or warehouse

        if not row_warehouse:
            frappe.throw(_("Warehouse is required for item {0}").format(item_code))

        batch_no = row.get("batch_no") if row.get("batch_no") != "-" else None
        serial_no = row.get("serial_no") if row.get("serial_no") != "-" else None

        has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")
        if has_batch and not batch_no:
            frappe.throw(_("Batch No is mandatory for item {0}").format(item_code))

        if purpose == "Opening Stock" and row.get("valuation_rate") is None:
            frappe.throw(_("Valuation Rate is mandatory for item {0} when posting Opening Stock").format(item_code))

        doc.append("items", {
            "item_code": item_code,
            "warehouse": row_warehouse,
            "qty": row.get("qty"),
            "valuation_rate": row.get("valuation_rate"),
            "serial_no": serial_no,
            "batch_no": batch_no,
            "use_serial_batch_fields": 1,
        })
        
    doc.run_method("set_missing_values")
    doc.insert()
    doc.submit()

    return {
        "name": doc.name,
        "status": "success",
        "message": f"Stock Reconciliation ({purpose}) {doc.name} submitted successfully"
    }