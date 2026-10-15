import json
import frappe
from frappe.utils import flt
from .utils import (
    build_sales_order_filters,
    get_extended_item_detail,
    sync_taxes,
    sync_sales_order_terms,
    get_naming_series_for_sales_order,
    _build_sales_order_box_detail
)
from custom_api.api.item.utils.item_utils import _get_tax
from ....api.buying.purchase_order.utils import _get_item_tax_template


def create_sales_order(data):
    company = frappe.defaults.get_user_default("Company")
    company_doc = frappe.get_cached_doc("Company", company)

    currency = data.get("currency") or company_doc.default_currency
    naming_series = get_naming_series_for_sales_order()
    payment_mode = data.get("payment_mode")

    sales_order = frappe.new_doc("Sales Order")

    sales_order.update(
        {
            "naming_series": naming_series,
            "title": data.get("title"),
            "customer": data.get("customerId"),
            "currency": currency,
            "conversion_rate": data.get("exchangeRate", 1),
            "transaction_date": data.get("postingDate"),
            "delivery_date": data.get("deliveryDate"),
            "po_no": data.get("customerPoNo"),
            "po_date": data.get("customerPoDate"),
            "tax_category": data.get("taxCategory"),
            "customer_address": data.get("billingAddress"),
            "shipping_address_name": data.get("shippingAddress"),
            "taxes_and_charges": data.get("salesTaxTemplate"),
            "order_type": data.get("orderType", "Sales"),
        }
    )

    sales_order.append("custom_extended_details", {
        "payment_mode": payment_mode
    })

    for item in data.get("items", []):
        sales_order.append(
            "items",
            {
                "item_code": item.get("itemCode"),
                "qty": item.get("quantity"),
                "uom": item.get("uom"),
                "discount_percentage": item.get("discount", 0),
                "price_list_rate": item.get("rate"),
                "delivery_date": item.get("deliveryDate") or data.get("deliveryDate"),
                # "warehouse": item.get("warehouse"),
                "item_tax_template": _get_item_tax_template(
                    item.get("itemCode"), data.get("taxCategory")
                ),
            },
        )

        # sales_order.append("custom_item_box_detail", _build_sales_order_box_detail(item))

    sync_taxes(sales_order, data)

    sales_order.insert(ignore_permissions=True)

    terms_payload = data.get("terms")
    if terms_payload:
        sync_sales_order_terms(sales_order, terms_payload)

    return sales_order


def update_sales_order(sales_order_id, data):
    sales_order = frappe.get_doc("Sales Order", sales_order_id)

    if sales_order.docstatus == 1:
        raise frappe.ValidationError(
            "Cannot edit a submitted Sales Order. Cancel it first."
        )

    company = sales_order.company
    company_doc = frappe.get_cached_doc("Company", company)
    currency = data.get("currency") or company_doc.default_currency
    payment_mode = data.get("payment_mode")

    field_map = {
        "title": "title",
        "customerId": "customer",
        "currency": "currency",
        "exchangeRate": "conversion_rate",
        "postingDate": "transaction_date",
        "deliveryDate": "delivery_date",
        "customerPoNo": "po_no",
        "customerPoDate": "po_date",
        "taxCategory": "tax_category",
        "billingAddress": "customer_address",
        "shippingAddress": "shipping_address_name",
        "salesTaxTemplate": "taxes_and_charges",
        "orderType": "order_type",
    }

    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(sales_order, v, data.get(k))
    if currency:
        sales_order.currency = currency

    payment_mode = data.get("paymentMode") or data.get("payment_mode")
    if payment_mode is not None:
        sales_order.set("custom_extended_details", [])
        sales_order.append("custom_extended_details", {
            "payment_mode": payment_mode
        })

    if "items" in data:
        sales_order.set("items", [])
        # sales_order.set("custom_item_box_detail", [])
        for item in data.get("items"):
            sales_order.append(
                "items",
                {
                    "item_code": item.get("itemCode"),
                    "qty": item.get("quantity"),
                    "uom": item.get("uom"),
                    "price_list_rate": item.get("rate"),
                    "discount_percentage": item.get("discount", 0),
                    "delivery_date": item.get("deliveryDate") or data.get("deliveryDate"),
                    # "warehouse": item.get("warehouse"),
                    "item_tax_template": _get_item_tax_template(
                        item.get("itemCode"),
                        data.get("taxCategory") or sales_order.tax_category,
                    ),
                },
            )

            # sales_order.append("custom_item_box_detail", _build_sales_order_box_detail(item))

    sync_taxes(sales_order, data)

    if "terms" in data:
        sales_order.payment_terms_template = None
        sales_order.set("payment_schedule", [])

    sales_order.save(ignore_permissions=True)
    terms_payload = data.get("terms")
    if terms_payload:
        sync_sales_order_terms(sales_order, terms_payload)

    return sales_order


def get_sales_order_by_id(sales_order_id):
    sales_order = frappe.get_doc("Sales Order", sales_order_id)
    customer_name, customer_tpin = frappe.db.get_value(
    "Customer",
    sales_order.customer,
    ["customer_name", "tax_id"]
)

    # box_details = getattr(sales_order, "custom_item_box_detail", None) or []

    data = {
        "id": sales_order.name,
        "title": sales_order.title,
        "customerId": sales_order.customer,
        "customerName": customer_name,
        "customerTpin": customer_tpin,
        "contact_email": sales_order.contact_email,
        "currency": sales_order.currency,
        "exchangeRate": sales_order.conversion_rate,
        "postingDate": sales_order.transaction_date,
        "deliveryDate": sales_order.delivery_date,
        "customerPoNo": sales_order.po_no,
        "customerPoDate": sales_order.po_date,
        "taxCategory": sales_order.tax_category,
        "customerAddressId": sales_order.customer_address,
        "billingAddress": sales_order.address_display,
        "shippingAddressId": sales_order.shipping_address_name,
        "shippingAddress": sales_order.shipping_address,
        "salesTaxTemplate": sales_order.taxes_and_charges,
        "status": sales_order.status,
        "docstatus": sales_order.docstatus,
        "roundingAdjustment": sales_order.rounding_adjustment,
        "roundedTotal": sales_order.rounded_total,
        "totalQty": sales_order.total_qty,
        "totalTax": sales_order.total_taxes_and_charges,
        "netTotal": sales_order.net_total,
        "grandTotal": sales_order.grand_total,
        "inWords": sales_order.in_words,
        "perDelivered": sales_order.per_delivered,
        "perBilled": sales_order.per_billed,
        "documentType": "Sales Order",
        "items": [],
        "taxes": [],
        "charges": [],
        "terms": {},
    }

    ext_details = getattr(sales_order, "custom_extended_details", None) or []
    if ext_details:
        data["payment_mode"] = ext_details[0].payment_mode

    for item in sales_order.items:
        tax_info = _get_tax(item.item_code, sales_order.tax_category)

        item_data = {
            "itemCode": item.item_code,
            "itemName": item.item_name,
            "uom": item.uom,
            "quantity": item.qty,
            "rate": item.price_list_rate,
            "discount": item.discount_percentage,
            "discountAmount": item.discount_amount,
            "amount": item.amount,
            "deliveryDate": item.delivery_date,
            # "warehouse": item.warehouse,
            "taxInfo": tax_info,
            "batchNo": getattr(item, "batch_no", None),
            "boxStart": None,
            "boxEnd": None
        }
        # for box in box_details:
        #     if box.item_code == item.item_code:
        #         item_data["boxStart"] = box.box_start
        #         item_data["boxEnd"] = box.box_end

        #         if not item_data["batchNo"] and box.batch_no:
        #             item_data["batchNo"] = box.batch_no
        #         break

        metadata = get_extended_item_detail(item.item_code)
        if metadata:
            meta = metadata[0]
            item_data.update(
                {
                    "hsnCode": meta.get("hsn_code"),
                    "packingUnit": meta.get("packing_unit"),
                    "packingSize": meta.get("packing_size"),
                }
            )

        data["items"].append(item_data)

    total_tax = 0
    total_charges = 0

    for tax in (getattr(sales_order, "taxes", None) or []):
        amount = tax.tax_amount or 0
        account = frappe.get_cached_value(
            "Account", tax.account_head, ["account_type", "account_name"], as_dict=True
        )

        account_type = account.account_type if account else None
        account_name = account.account_name if account else None

        row = {
            "accountHead": tax.account_head,
            "accountName": account_name,
            "chargeType": tax.charge_type,
            "rate": tax.rate,
            "amount": amount,
            "description": tax.description,
        }

        if account_type == "Tax":
            data["taxes"].append(row)
            total_tax += amount
        else:
            data["charges"].append(row)
            total_charges += amount

    data["totalCalculatedTax"] = total_tax
    data["totalCalculatedCharges"] = total_charges

    if sales_order.tc_name and frappe.db.exists(
        "Terms and Conditions", sales_order.tc_name
    ):
        tc_content = frappe.db.get_value(
            "Terms and Conditions", sales_order.tc_name, "terms"
        )
        try:
            data["terms"]["selling"] = json.loads(tc_content)
        except Exception:
            data["terms"]["selling"] = tc_content

    attachments = frappe.db.get_all(
        "File",
        filters={
            "attached_to_doctype": "Sales Order",
            "attached_to_name": sales_order_id,
        },
        fields=[
            "name",
            "file_name",
            "file_url",
            "file_size",
            "file_type",
            "is_private",
            "creation",
        ],
        order_by="creation desc",
    )
    data["attachments"] = [att for att in attachments]

    return data


def get_sales_orders(filters=None, page=1, page_size=20, search=None):
    filters = filters or {}

    frappe_filters = build_sales_order_filters(filters)

    or_filters = []
    if search:
        search = str(search).strip()
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["customer", "like", f"%{search}%"],
            ["customer_name", "like", f"%{search}%"],
            ["status", "like", f"%{search}%"],
            ["currency", "like", f"%{search}%"],
            ["po_no", "like", f"%{search}%"],
        ]

    start = (page - 1) * page_size
    order_by = filters.get("order_by", "creation desc")
    sales_orders = frappe.get_all(
        "Sales Order",
        filters=frappe_filters,
        or_filters=or_filters if search else None,
        fields=[
            "name",
            "customer",
            "customer_name",
            "transaction_date",
            "delivery_date",
            "po_no",
            "base_grand_total",
            "grand_total",
            "currency",
            "status",
            "per_delivered",
            "per_billed",
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by=order_by,
    )

    total_sales_orders = len(
        frappe.get_all(
            "Sales Order",
            filters=frappe_filters,
            or_filters=or_filters if search else None,
            pluck="name",
        )
    )

    total_pages = (total_sales_orders + page_size - 1) // page_size

    for so in sales_orders:
        so["id"] = so.pop("name")
        so["customer"] = so.pop("customer")
        so["customerName"] = so.pop("customer_name")
        so["postingDate"] = so.pop("transaction_date")
        so["deliveryDate"] = so.pop("delivery_date")
        so["customerPoNo"] = so.pop("po_no")
        so["total"] = so.pop("grand_total")
        so["baseGrandTotal"] = so.pop("base_grand_total")
        so["perDelivered"] = so.pop("per_delivered")
        so["perBilled"] = so.pop("per_billed")
        so["documentType"] = "Sales Order"

    return sales_orders, total_sales_orders, total_pages


def delete_sales_order(sales_order_id):
    sales_order = frappe.get_doc("Sales Order", sales_order_id)
    if sales_order.docstatus == 1:
        raise frappe.ValidationError(
            "Cannot delete a submitted Sales Order. Cancel it first."
        )

    frappe.db.set_value(
        "Sales Order",
        sales_order_id,
        {"tc_name": None, "payment_terms_template": None},
        update_modified=False,
    )

    frappe.delete_doc("Sales Order", sales_order_id, ignore_permissions=True)

    tc_name = f"{sales_order_id} Terms"
    if frappe.db.exists("Terms and Conditions", tc_name):
        frappe.delete_doc(
            "Terms and Conditions", tc_name, ignore_permissions=True, force=True
        )

    pt_name = f"{sales_order_id} PT"
    if frappe.db.exists("Payment Terms Template", pt_name):
        template_doc = frappe.get_doc("Payment Terms Template", pt_name)
        terms_to_delete = [t.payment_term for t in template_doc.terms]

        frappe.delete_doc(
            "Payment Terms Template", pt_name, ignore_permissions=True, force=True
        )

        for term in terms_to_delete:
            is_used_elsewhere = frappe.db.exists(
                "Payment Terms Template Detail", {"payment_term": term}
            )
            if not is_used_elsewhere:
                try:
                    frappe.delete_doc("Payment Term", term, ignore_permissions=True)
                except frappe.exceptions.LinkExistsError:
                    pass


def update_sales_order_status(sales_order_id, action, payload=None):
    payload = payload or {}

    sales_order = frappe.get_doc("Sales Order", sales_order_id)

    if not frappe.has_permission("Sales Order", "write", sales_order):
        raise frappe.PermissionError("No permission to modify this sales order")

    if action == "approved":
        if sales_order.docstatus == 1:
            raise frappe.ValidationError("Sales Order is already approved.")
        if sales_order.docstatus == 2:
            raise frappe.ValidationError(
                "Cannot approve a cancelled sales order. Please amend it first."
            )

        sales_order.submit()

        return {
            "id": sales_order.name,
            "status": sales_order.status,
            "docstatus": sales_order.docstatus,
        }

    elif action == "cancelled":
        if sales_order.docstatus == 2:
            raise frappe.ValidationError("Sales Order is already cancelled.")
        if sales_order.docstatus == 0:
            raise frappe.ValidationError(
                "Cannot cancel a Draft sales order. Submit it first."
            )

        sales_order.cancel()

        return {
            "id": sales_order.name,
            "status": sales_order.status,
            "docstatus": sales_order.docstatus,
        }

    elif action == "amend":
        if sales_order.docstatus == 0:
            raise frappe.ValidationError("Sales Order is already in Draft state.")
        if sales_order.docstatus == 1:
            raise frappe.ValidationError(
                "Cannot amend an approved sales order. Cancel it first."
            )

        amended_doc = frappe.copy_doc(sales_order)
        amended_doc.amended_from = sales_order.name
        amended_doc.docstatus = 0
        amended_doc.insert()

        return {
            "id": amended_doc.name,
            "status": amended_doc.status,
            "docstatus": amended_doc.docstatus,
        }

    elif action == "closed":
        if sales_order.docstatus != 1:
            raise frappe.ValidationError(
                "Only a submitted Sales Order can be closed."
            )
        if sales_order.status == "Closed":
            raise frappe.ValidationError("Sales Order is already closed.")

        sales_order.update_status("Closed")

        return {
            "id": sales_order.name,
            "status": sales_order.status,
            "docstatus": sales_order.docstatus,
        }

    elif action == "reopened":
        if sales_order.status != "Closed":
            raise frappe.ValidationError("Only a closed Sales Order can be reopened.")

        sales_order.update_status("Draft")

        return {
            "id": sales_order.name,
            "status": sales_order.status,
            "docstatus": sales_order.docstatus,
        }

    else:
        raise frappe.ValidationError(
            "Invalid action. Allowed: approved, cancelled, amend, closed, reopened"
        )