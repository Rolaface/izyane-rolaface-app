import json
import frappe
from frappe.utils import flt, cint, add_days
from ....api.buying.purchase_order.utils import _get_item_tax_template
from .utils import (
    ensure_batch,
    sync_invoice_terms,
    sync_taxes,
    _build_sales_invoice_box_detail,
    _build_additional_detail,
    validate_receivable_account_for_currency,
    get_extended_item_detail,
    get_payment_information,
    build_sales_invoice_filters
)

from custom_api.api.item.utils.item_utils import _get_tax

def create_sales_invoice(data):
    company = frappe.defaults.get_user_default("Company")
    company_doc = frappe.get_cached_doc("Company", company)

    currency = data.get("currency") or company_doc.default_currency
    cost_center = data.get("costCenter") or company_doc.cost_center
    account = validate_receivable_account_for_currency(currency)

    invoice = frappe.new_doc("Sales Invoice")

    invoice.update({
        "customer": data.get("customerId"),
        "currency": currency,
        "conversion_rate": data.get("exchangeRate", 1),
        "posting_date": data.get("postingDate"),
        "due_date": data.get("dueDate"),
        "tax_category": data.get("tax_category"),
        "update_stock": 1 if data.get("updateStock") else 0,
        "set_posting_time": 1 if data.get("updateStock") else 0,
        "set_warehouse": data.get("warehouse"),
        "customer_address": data.get("billingAddress"),
        "shipping_address_name": data.get("shippingAddress"),
        "taxes_and_charges": data.get("salesTaxTemplate"),
        "cost_center": cost_center,
        "debit_to": account,
    })

    for item in data.get("items", []):
        item_code = item.get("itemCode")
        batch_no = item.get("batchNo") or item.get("batch_no")
        mfg_date = item.get("mfgDate") or item.get("mfg_date")
        exp_date = item.get("expDate") or item.get("exp_date")

        if batch_no:
            ensure_batch(item_code, batch_no, mfg_date, exp_date)

        invoice.append("items", {
            "item_code": item_code,
            "qty": item.get("quantity"),
            "rate": item.get("rate"),
            "warehouse": item.get("warehouse", data.get("warehouse")),
            "batch_no": batch_no,
            "item_tax_template": _get_item_tax_template(item_code, data.get("tax_category")),
        })

        invoice.append("custom_item_box_detail", _build_sales_invoice_box_detail(item))

    additional_details = _build_additional_detail(data)
    if additional_details:
        invoice.append("custom_details", additional_details)

    sync_taxes(invoice, data)

    invoice.insert(ignore_permissions=True)

    terms_payload = data.get("terms")
    if terms_payload:
        sync_invoice_terms(invoice, terms_payload)

    return invoice


def update_sales_invoice(invoice_id, data):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    if invoice.docstatus == 1:
        raise frappe.ValidationError("Cannot edit a submitted Sales Invoice. Cancel it first.")
    
    company = invoice.company
    company_doc = frappe.get_cached_doc("Company", company)

    currency = data.get("currency") or company_doc.default_currency
    cost_center = data.get("costCenter") or invoice.cost_center or company_doc.cost_center

    field_map = {
        "customerId": "customer",
        "currency": "currency",
        "exchangeRate": "conversion_rate",
        "postingDate": "posting_date",
        "dueDate": "due_date",
        "tax_category": "tax_category",
        "warehouse": "set_warehouse",
        "billingAddress": "customer_address",
        "shippingAddress": "shipping_address_name",
        "salesTaxTemplate": "taxes_and_charges",
    }

    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(invoice, v, data.get(k))

    if currency: invoice.currency = currency
    if cost_center: invoice.cost_center = cost_center
    if data.get("updateStock") is not None:
        invoice.update_stock = 1 if data.get("updateStock") else 0
        invoice.set_posting_time = 1 if data.get("updateStock") else 0

    if "items" in data:
        invoice.set("items", [])
        invoice.set("custom_item_box_detail", [])

        for item in data.get("items"):
            item_code = item.get("itemCode")
            batch_no = item.get("batchNo") or item.get("batch_no")
            mfg_date = item.get("mfgDate") or item.get("mfg_date")
            exp_date = item.get("expDate") or item.get("exp_date")

            if batch_no:
                ensure_batch(item_code, batch_no, mfg_date, exp_date)

            invoice.append("items", {
                "item_code": item_code,
                "qty": item.get("quantity"),
                "rate": item.get("rate"),
                "warehouse": item.get("warehouse", invoice.set_warehouse),
                "batch_no": batch_no,
                "item_tax_template": _get_item_tax_template(item_code, data.get("tax_category")), 
            })
            invoice.append("custom_item_box_detail", _build_sales_invoice_box_detail(item))

    sync_taxes(invoice, data)

    if "paymentMode" in data or "payment_mode" in data:
        detail = _build_additional_detail(data)
        invoice.set("custom_details", [])
        if detail:
            invoice.append("custom_details", detail)

    invoice.save(ignore_permissions=True)

    terms_payload = data.get("terms")
    if terms_payload:
        sync_invoice_terms(invoice, terms_payload)

    return invoice

def get_sales_invoice_by_id(invoice_id):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    customer = frappe.get_doc("Customer", invoice.customer)

    box_details = invoice.get("custom_item_box_detail", [])
    custom_details = invoice.get("custom_details", [])

    data = {
        "id": invoice.name,
        "customerId": invoice.customer,
        "customerName": customer.customer_name,
        "customerTpin": customer.tax_id,
        "currency": invoice.currency,
        "exchangeRate": invoice.conversion_rate,
        "postingDate": invoice.posting_date,
        "dueDate": invoice.due_date,
        "tax_category": invoice.tax_category,
        "updateStock": bool(invoice.update_stock),
        "warehouse": invoice.set_warehouse,
        "billingAddress": invoice.address_display,
        "shippingAddress": invoice.shipping_address,
        "salesTaxTemplate": invoice.taxes_and_charges,
        "status": invoice.status,
        "docstatus": invoice.docstatus,
        "outstanding_amount": invoice.outstanding_amount,
        # "destnCountryCd": customer.outstanding_amount,
        "costCenter": invoice.cost_center,
        "roundingAdjustment": invoice.rounding_adjustment,
        "roundedTotal": invoice.rounded_total,
        "total_qty": invoice.total_qty,
        "total_tax": invoice.total_taxes_and_charges,
        "total": invoice.total,
        "net_total": invoice.net_total,
        "grand_total": invoice.grand_total,
        "total_advance": invoice.total_advance,
        "in_words": invoice.in_words,
        "items": [],
        "taxes": [],
        "charges": [],
        "terms": {},
    }

    payment_mode = custom_details[0].payment_mode if custom_details else None

    data["paymentInformation"] = get_payment_information(
        payment_mode,
        invoice.company
    )

    for item in invoice.items:
        tax = _get_tax(item.item_code, invoice.tax_category)

        item_data = {
            "itemCode": item.item_code,
            "itemName": item.item_name,
            "uom": item.uom ,
            "quantity": item.qty,
            "rate": item.rate,
            "warehouse": item.warehouse,
            "batchNo": item.batch_no,
            "costCenter": item.cost_center,
            "itemTaxTemplate": item.item_tax_template,
            "taxInfo": tax,
        }

        if item.batch_no:
            batch_info = frappe.db.get_value(
                "Batch",
                item.batch_no,
                ["manufacturing_date", "expiry_date"],
                as_dict=True,
            )
            if batch_info:
                item_data["mfgDate"] = batch_info.manufacturing_date
                item_data["expDate"] = batch_info.expiry_date

        for box in box_details:
            if box.item_code == item.item_code and (
                box.batch_no == item.batch_no or not box.batch_no
            ):
                item_data["boxStart"] = box.box_start
                item_data["boxEnd"] = box.box_end
                break

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

    for tax in invoice.get("taxes", []):
        row = {
            "accountHead": tax.account_head,
            "rate": tax.rate,
            "amount": tax.tax_amount,
        }

        account_type = frappe.get_cached_value(
            "Account", tax.account_head, "account_type"
        )

        if account_type == "Tax":
            data["taxes"].append(row)
        else:
            data["charges"].append(row)

    if invoice.tc_name and frappe.db.exists("Terms and Conditions", invoice.tc_name):
        tc_content = frappe.db.get_value(
            "Terms and Conditions", invoice.tc_name, "terms"
        )
        try:
            data["terms"]["selling"] = json.loads(tc_content)
        except Exception:
            data["terms"]["selling"] = tc_content

    return data

def get_sales_invoices(filters=None, page=1, page_size=20, search=None):
    filters = filters or {}

    allowed_filters = {
        key: filters.get(key)
        for key in [
            "customer",
            "status",
            "from_date",
            "to_date",
            "company",
            "minOutstanding",
            "maxOutstanding",
        ]
        if filters.get(key) is not None
    }

    frappe_filters = build_sales_invoice_filters(allowed_filters)

    or_filters = []
    if search:
        search = str(search).strip()
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["customer", "like", f"%{search}%"],
            ["customer_name", "like", f"%{search}%"],
            ["status", "like", f"%{search}%"],
            ["currency", "like", f"%{search}%"],
        ]

    start = (page - 1) * page_size

    invoices = frappe.get_all(
        "Sales Invoice",
        filters=frappe_filters,
        or_filters=or_filters if search else None,
        fields=[
            "name",
            "customer",
            "customer_name",
            "posting_date",
            "due_date",
            "base_grand_total",
            "grand_total",
            "currency",
            "conversion_rate",
            "outstanding_amount",
            "tax_category",
            "cost_center",
            "status",
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by="creation desc",
    )

    total_invoices = len(
        frappe.get_all(
            "Sales Invoice",
            filters=frappe_filters,
            or_filters=or_filters if search else None,
            pluck="name",
        )
    )

    total_pages = (total_invoices + page_size - 1) // page_size

    for inv in invoices:
        inv["id"] = inv.pop("name")
        inv["customerId"] = inv.pop("customer")
        inv["customerName"] = inv.pop("customer_name")
        inv["invoiceDate"] = inv.pop("posting_date")
        inv["dueDate"] = inv.pop("due_date")
        inv["total"] = inv.pop("grand_total")
        inv["baseGrandTotal"] = inv.pop("base_grand_total")
        inv["exchangeRate"] = inv.pop("conversion_rate")
        inv["outstandingAmount"] = inv.pop("outstanding_amount")
        inv["costCenter"] = inv.pop("cost_center")
        inv["taxCategory"] = inv.pop("tax_category")

    return invoices, total_invoices, total_pages


def delete_sales_invoice(invoice_id):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    if invoice.docstatus == 1:
        raise frappe.ValidationError(
            "Cannot delete a submitted Sales Invoice. Cancel it first."
        )

    frappe.db.set_value(
        "Sales Invoice",
        invoice_id,
        {"tc_name": None, "payment_terms_template": None},
        update_modified=False,
    )

    frappe.delete_doc("Sales Invoice", invoice_id, ignore_permissions=True)

    tc_name = f"{invoice_id} Terms"
    if frappe.db.exists("Terms and Conditions", tc_name):
        frappe.delete_doc(
            "Terms and Conditions", tc_name, ignore_permissions=True, force=True
        )

    pt_name = f"{invoice_id} PT"
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


def update_sales_invoice_status(invoice_id, action):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    if not frappe.has_permission("Sales Invoice", "write", invoice):
        raise frappe.PermissionError("No permission to modify this invoice")

    if action == "approved":
        if invoice.docstatus == 1:
            raise frappe.ValidationError("Invoice is already approved.")
        if invoice.docstatus == 2:
            raise frappe.ValidationError(
                "Cannot approve a cancelled invoice. Please amend it first."
            )

        invoice.submit()

        return {
            "id": invoice.name,
            "status": invoice.status,
            "docstatus": invoice.docstatus,
        }

    elif action == "cancelled":
        if invoice.docstatus == 2:
            raise frappe.ValidationError("Invoice is already cancelled.")
        if invoice.docstatus == 0:
            raise frappe.ValidationError(
                "Cannot cancel a Draft invoice. Submit it first."
            )

        invoice.cancel()

        return {
            "id": invoice.name,
            "status": invoice.status,
            "docstatus": invoice.docstatus,
        }

    elif action == "amend":
        if invoice.docstatus == 0:
            raise frappe.ValidationError("Invoice is already in Draft state.")
        if invoice.docstatus == 1:
            raise frappe.ValidationError(
                "Cannot amend a approved invoice. Cancel it first."
            )

        amended_doc = frappe.copy_doc(invoice)
        amended_doc.amended_from = invoice.name
        amended_doc.docstatus = 0
        amended_doc.insert()

        return {
            "id": amended_doc.name,
            "status": amended_doc.status,
            "docstatus": amended_doc.docstatus,
        }

    else:
        raise frappe.ValidationError("Invalid action. Allowed: approved, cancelled, amend")