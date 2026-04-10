import frappe
from frappe.utils import nowdate

def create_item_prices(item_doc, data: dict):

    selling_price = data.get("sellingPrice")
    buying_price = data.get("buyingPrice")

    uom = item_doc.stock_uom or "Nos"
    currency = frappe.defaults.get_global_default("currency")

    if selling_price:
        _create_price(
            item_code=item_doc.name,
            price=selling_price,
            price_list="Standard Selling",
            uom=uom,
            currency=currency,
            selling=1,
            buying=0
        )

    if buying_price:
        _create_price(
            item_code=item_doc.name,
            price=buying_price,
            price_list="Standard Buying",
            uom=uom,
            currency=currency,
            selling=0,
            buying=1,
            supplier=data.get("vendorInfo").get("preferredVendor") if data.get("vendorInfo") else None
        )

def _create_price(item_code, price, price_list, uom, currency, selling=0, buying=0, supplier=None):

    existing_price = frappe.db.exists("Item Price", {
                                        "item_code": item_code,
                                        "price_list": price_list,
                                        "uom": uom
                                    })
    if existing_price:
        doc = frappe.get_doc("Item Price", existing_price)
        doc.price_list_rate = price
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({
            "doctype": "Item Price",
            "item_code": item_code,
            "price_list": price_list,
            "price_list_rate": price,
            "uom": uom,
            "currency": currency,
            "valid_from": nowdate(),
            "selling": selling,
            "buying": buying,
            "supplier": supplier
        })
        doc.insert(ignore_permissions=True)
