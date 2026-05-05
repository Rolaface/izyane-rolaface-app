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
        "is_stock_item": data.get("is_stock_item", 1),
        "is_purchase_item": data.get("is_purchase_item",1),
        "is_sales_item": data.get("is_sales_item", 1),

        # Link Brand
        "brand": brand,

        # Inventory
        "valuation_method": data.get("inventoryInfo", {}).get("valuationMethod") or "FIFO",
        "has_batch_no": 1 if data.get("batchInfo", {}).get("has_batch_no") else 0,
        "has_expiry_date": 1 if data.get("batchInfo", {}).get("has_expiry_date") else 0,
        "shelf_life_in_days": int(data.get("batchInfo", {}).get("shelfLife") or 0),
        
        "country_of_origin": data.get("countryOfOrigin") or "",

        "uoms": [
            {
                "uom": data.get("unitOfMeasureCd") or "Nos",
                "conversion_factor": 1
            }
        ],
        "taxes": _map_taxes(data),
        "custom_item_metadata": _save_item_metadata(data)
    }

def _map_taxes(data):
    tax_info_list = data.get("taxInfo")

    if not tax_info_list:
        return []

    mapped_taxes = []

    for tax_info in tax_info_list:

        tax_name = tax_info.get("taxName")
        tax_category = tax_info.get("taxCategory")

        if not tax_name and not tax_category:
            continue
        
        if not tax_name:
            frappe.throw(f"Tax' is required.")

        if not tax_category:
            frappe.throw(f"TaxCategory is required.")

        mapped_taxes.append({
            "item_tax_template": tax_name,
            "tax_category": tax_category
        })

    return mapped_taxes

def _save_item_metadata(data):
    return [{
        "packing_unit": data.get("packingUnit") or "",
        "packing_size": data.get("packingSize") or "",
        "length": data.get("dimensionLength") or "",
        "width": data.get("dimensionWidth") or "",
        "height": data.get("dimensionHeight") or "",
        "re_order_level": data.get("inventoryInfo", {}).get("reorderLevel") or "",
        "min_stock_level": data.get("inventoryInfo", {}).get("minStockLevel") or "",
        "max_stock_level": data.get("inventoryInfo", {}).get("maxStockLevel") or "",
        "hsn_code": data.get("itemClassCode") or "",
    }]

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

    batch_info = data.get("batchInfo", {})
    if batch_info.get("has_expiry_date") and not batch_info.get("shelfLife"):
        frappe.throw("Shelf life is required when expiry tracking is enabled")

def map_item_response(item, tax_category=None):

    # Prices
    selling_price = _get_price(item.name, "Standard Selling")
    buying_price = _get_price(item.name, "Standard Buying")

    # Tax
    tax = _get_tax(item.name, tax_category)

    item_metadata = frappe.db.get_value("Custom Item Details", 
                                        {"parent": item.name}, 
                                        ["*"], as_dict=True)

    return {
        "id": item.name,
        "itemName": item.item_name,
        "itemGroup": item.item_group,
        "unitOfMeasureCd": item.stock_uom,

        "sellingPrice": selling_price["price_list_rate"] if selling_price else 0.0,
        "buyingPrice": buying_price["price_list_rate"] if buying_price else 0.0,
        "vendorInfo": {"preferredVendor": buying_price.get("supplier") if buying_price else "",
                       "preferredVendorName": buying_price.get("supplier_name") if buying_price else ""},
        "brand": item.brand or "",
        "description": item.description or "",

        "weight": str(item.weight_per_unit or 0),
        "weightUnit": item.weight_uom or "",

        "taxInfo": tax,

        "countryOfOrigin": item.country_of_origin or "",

        "is_stock_item": item.is_stock_item,
        "is_purchase_item": item.is_purchase_item,
        "is_sales_item": item.is_sales_item,

        "dimensionLength": item_metadata.length if item_metadata else "",
        "dimensionWidth": item_metadata.width if item_metadata else "",
        "dimensionHeight": item_metadata.height if item_metadata else "",
        "packingUnit": item_metadata.packing_unit if item_metadata else "",
        "packingSize": item_metadata.packing_size if item_metadata else "",
        "itemClassCode": item_metadata.hsn_code if item_metadata else "",
        "inventoryInfo": {
            "valuationMethod": item.valuation_method or "",
            "trackingMethod": _get_tracking_method(item),
            "reorderLevel": item_metadata.get("re_order_level") if item_metadata else "0",
            "minStockLevel": item_metadata.get("min_stock_level") if item_metadata else "0",
            "maxStockLevel": item_metadata.get("max_stock_level") if item_metadata else "0",
        },

        "batchInfo": {
            "has_batch_no": bool(item.has_batch_no),
            "has_expiry_date": bool(item.has_expiry_date),
            "shelfLife": item.shelf_life_in_days or 0
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

    if not price:
        return {}

    supplier_name = ""

    if price.supplier:
        supplier_name = frappe.db.get_value(
                        "Supplier",
                        price.supplier,
                        "supplier_name"
                    )

    return {
        "price_list_rate": price.price_list_rate or 0,
        "supplier": price.supplier or "",
        "supplier_name": supplier_name
    }

def _get_tax(item_code, tax_category=None):
    filters = {"parent": item_code}

    if tax_category:
        filters["tax_category"] = tax_category

    item_taxes = frappe.get_all(
        "Item Tax",
        filters=filters,
        fields=["item_tax_template", "tax_category"]
    )

    if not item_taxes:
        return []

    result = []
    total_tax_rate = 0
    for tax in item_taxes:
        tax_rates = []
        tax_template_title = ""

        if tax.item_tax_template:
            tax_template_title = frappe.db.get_value(
                "Item Tax Template", 
                tax.item_tax_template, 
                "title"
            )

            tax_details = frappe.get_all(
                "Item Tax Template Detail",
                filters={"parent": tax.item_tax_template},
                fields=["tax_type", "tax_rate"]
            )

            tax_rates = tax_details

        total_tax_rate += sum([t.tax_rate for t in tax_rates])
        
        result.append({
            "taxCategory": tax.tax_category or "",
            "taxName":  tax.item_tax_template or "",
            "taxTitle": tax_template_title or "",
            "taxRates": tax_rates,
            "totalTaxRate": total_tax_rate
        })

    return result

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
    item_doc.is_stock_item = data.get("is_stock_item")
    item_doc.is_purchase_item = data.get("is_purchase_item")
    item_doc.is_sales_item = data.get("is_sales_item")
    item_doc.has_batch_no = 1 if batch_info.get("has_batch_no") else 0
    item_doc.has_expiry_date = 1 if batch_info.get("has_expiry_date") else 0
    item_doc.shelf_life_in_days = int(
    data.get("batchInfo", {}).get("shelfLife") or 0)

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
            if not tax_name and not tax_category:
                continue

            if not tax_name:
                frappe.throw((f"Tax Type is required"))

            if not tax_category:
                frappe.throw(f"TaxCategory is required.")
            item_doc.append("taxes", {
            "item_tax_template": tax_name,
            "tax_category": tax_category
        })
            
def _update_item_metadata(item_doc, data):

    item_doc.custom_item_metadata = []
    item_doc.append("custom_item_metadata", {
        "packing_unit": data.get("packingUnit") or "",
        "packing_size": data.get("packingSize") or "",
        "length": data.get("dimensionLength") or "",
        "width": data.get("dimensionWidth") or "",
        "height": data.get("dimensionHeight") or "",
        "re_order_level": data.get("inventoryInfo", {}).get("reorderLevel") or "",
        "min_stock_level": data.get("inventoryInfo", {}).get("minStockLevel") or "",
        "max_stock_level": data.get("inventoryInfo", {}).get("maxStockLevel") or "",
        "hsn_code": data.get("itemClassCode") or "",
    })
