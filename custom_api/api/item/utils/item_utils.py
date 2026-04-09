import frappe

def map_to_frappe_item(data: dict, brand: str) -> dict:

    return {
        "doctype": "Item",
        "item_name": data.get("itemName"),
        "item_group": data.get("itemGroup"),
        "description": data.get("description"),

        # Stock & UOM
        "stock_uom": data.get("unitOfMeasureCd") or "Nos",
        "weight_per_unit": float(data.get("weight") or 0),
        "weight_uom": data.get("weightUnit") or "Kg",

        # Flags
        "is_stock_item": 1,
        "is_purchase_item": 1,
        "is_sales_item": 1,

        # Link Brand
        "brand": brand,

        # Inventory
        "valuation_method": data.get("inventoryInfo", {}).get("valuationMethod") or "FIFO",
        "has_batch_no": 1 if data.get("batchInfo", {}).get("has_batch_no") else 0,
        "has_expiry_date": 1 if data.get("batchInfo", {}).get("has_expiry_date") else 0,
        
        "uoms": [
            {
                "uom": data.get("unitOfMeasureCd") or "Nos",
                "conversion_factor": 1
            }
        ],
        "taxes": _map_taxes(data),
    }

def _map_taxes(data):
    tax_info_list = data.get("taxInfo")

    if not tax_info_list:
        return []

    mapped_taxes = []

    for tax_info in tax_info_list:

        tax_name = tax_info.get("taxName")
        tax_category = tax_info.get("taxCategory")

        if not tax_name:
            frappe.throw((f"Tax Type is required"))

        mapped_taxes.append({
            "item_tax_template": tax_name,
            "tax_category": tax_category
        })

    return mapped_taxes

def validate_item_payload(data):

    required_fields = ["itemName", "itemGroup"]

    for field in required_fields:
        if not data.get(field):
            frappe.throw(f"{field} is required")

    # Example validation
    if data.get("sellingPrice") and float(data.get("sellingPrice")) < 0:
        frappe.throw("Selling price cannot be negative")

    if data.get("buyingPrice") and float(data.get("buyingPrice")) < 0:
        frappe.throw("Buying price cannot be negative")

def map_item_response(item):

    # Prices
    selling_price = _get_price(item.name, "Standard Selling")
    buying_price = _get_price(item.name, "Standard Buying")

    # Tax
    tax = _get_tax(item.name)

    # Reorder
    reorder = _get_reorder(item.name)

    return {
        "id": item.name,
        "itemName": item.item_name,
        "itemGroup": item.item_group,
        "unitOfMeasureCd": item.stock_uom,

        "sellingPrice": selling_price.price_list_rate if selling_price else 0.0,
        "buyingPrice": buying_price.price_list_rate if buying_price else 0.0,
        "vendorInfo": {"preferredVendor": buying_price.get("supplier") if buying_price else ""},
        "brand": item.brand or "",
        "description": item.description or "",

        "weight": str(item.weight_per_unit or 0),
        "weightUnit": item.weight_uom or "",

        "taxInfo": tax,

        "inventoryInfo": {
            "valuationMethod": item.valuation_method or "",
            "trackingMethod": _get_tracking_method(item),
            "reorderLevel": reorder.get("reorder_level", "0"),
            "minStockLevel": reorder.get("min_qty", "0"),
        },

        "batchInfo": {
            "has_batch_no": bool(item.has_batch_no),
            "has_expiry_date": bool(item.has_expiry_date),
        }
    }

def _get_price(item_code, price_list):
    price = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item_code,
            "price_list": price_list
        },
        ["price_list_rate", "supplier"],
        as_dict=True
    )
    return price


def _get_tax(item_code):
    tax = frappe.db.get_value(
        "Item Tax",
        {"parent": item_code},
        ["item_tax_template", "tax_category"],
        as_dict=True
    )

    if not tax:
        return {}

    return {
        "taxCategory": tax.tax_category or "",
        "taxName": tax.item_tax_template or "",
    }


def _get_reorder(item_code):
    reorder = frappe.db.get_value(
        "Item Reorder",
        {"parent": item_code},
        ["warehouse_reorder_level", "warehouse_reorder_qty"],
        as_dict=True
    )

    if not reorder:
        return {}

    return {
        "reorder_level": reorder.warehouse_reorder_level,
        "min_qty": reorder.warehouse_reorder_qty
    }


def _get_tracking_method(item):
    if item.has_batch_no:
        return "batch"
    if item.has_expiry_date:
        return "expiry"
    return "none"

def _update_basic_fields(item_doc, data, brand):

    item_doc.item_name = data.get("itemName")
    item_doc.item_group = data.get("itemGroup")
    item_doc.description = data.get("description")

    item_doc.brand = brand

    item_doc.stock_uom = data.get("unitOfMeasureCd") or "Nos"

    item_doc.weight_per_unit = float(data.get("weight") or 0)
    item_doc.weight_uom = data.get("weightUnit") or "Kg"

    item_doc.valuation_method = data.get("inventoryInfo", {}).get("valuationMethod") or "FIFO"

    batch_info = data.get("batchInfo", {})

    item_doc.has_batch_no = 1 if batch_info.get("has_batch_no") else 0
    item_doc.has_expiry_date = 1 if batch_info.get("has_expiry_date") else 0
    item_doc.end_of_life = batch_info.get("endOfLife") or "2099-12-31"

def _update_uom(item_doc, data):

    item_doc.uoms = []

    item_doc.append("uoms", {
        "uom": data.get("unitOfMeasureCd") or "Nos",
        "conversion_factor": 1
    })

def _update_taxes(item_doc, data):

    item_doc.taxes = []

    tax_info_list = data.get("taxInfo", [])

    if tax_info_list:
        for tax_info in tax_info_list:

            tax_name = tax_info.get("taxName")
            tax_category = tax_info.get("taxCategory")

            if not tax_name:
                frappe.throw((f"Tax Type is required"))

            item_doc.append("taxes", {
            "item_tax_template": tax_name,
            "tax_category": tax_category
        })