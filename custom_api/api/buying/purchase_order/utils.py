from custom_api.api.selling.sales_invoice.utils import ensure_batch
import frappe

def _get(data, key, default=None):
    return data.get(key) if data.get(key) not in [None, "", "0"] else default

def _to_list(value):
    if not value:
        return []
    return value if isinstance(value, list) else [value]

def _get_supplier_category(supplier):
    return frappe.db.get_value("Supplier", supplier, "tax_category") or ""

def build_items(items, supplier):

    po_items = []
    supplier_category = _get_supplier_category(supplier)

    for item in items:
        batch_no = item.get("batchNo")
        item_code = item.get("itemCode")
        mfg_date = item.get("mfgDate")
        exp_date = item.get("expDate")

        if batch_no:
            ensure_batch(item_code, batch_no, mfg_date, exp_date)

        if not item_code:
            frappe.throw("item_code is required")

        item_tax_template = _get_item_tax_template(item_code, supplier_category)

        item_dict = {
            "item_code": item_code,
            "item_name": item.get("itemName"),
            "qty": float(item.get("quantity", 1)),
            "rate": float(item.get("rate", 0)),
            "schedule_date": item.get("requiredBy"),
            "warehouse": item.get("warehouse"),
            "uom": item.get("uom"),
            "item_tax_template": item_tax_template
        }

        if batch_no:
            item_dict["batch_no"] = batch_no

        po_items.append(item_dict)

    return po_items

def _get_item_tax_template(item_code, supplier_category):

    taxes = frappe.get_all(
        "Item Tax",
        filters={"parent": item_code},
        fields=["item_tax_template", "tax_category"]
    )

    for tax in taxes:
        if tax.get("tax_category") == supplier_category:
            return tax.get("item_tax_template")

    return None


