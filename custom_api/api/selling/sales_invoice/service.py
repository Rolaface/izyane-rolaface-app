import json
import re
import traceback
import frappe
from frappe.utils import flt, cint, add_days, now
from ....api.buying.purchase_order.utils import _get_item_tax_template
from erpnext.selling.doctype.customer.customer import get_customer_outstanding
from .utils import (
    ensure_batch,
    sync_invoice_terms,
    sync_taxes,
    _build_sales_invoice_box_detail,
    _build_additional_detail,
    validate_receivable_account_for_currency,
    get_extended_item_detail,
    get_payment_information,
    build_sales_invoice_filters,
    get_already_credited_qty,
    get_lpo_tax_template,
    get_zero_rated_tax_template
)

from custom_api.api.item.utils.item_utils import _get_tax

def create_sales_invoice(data):
    company = frappe.defaults.get_user_default("Company")
    company_doc = frappe.get_cached_doc("Company", company)

    currency = data.get("currency") or company_doc.default_currency
    cost_center = data.get("costCenter") or company_doc.cost_center
    account = validate_receivable_account_for_currency(currency)

    invoice = frappe.new_doc("Sales Invoice")
    invoice_type = data.get("invoiceType")

    is_lpo_category = invoice_type == "LPO"
    is_tot_category = invoice_type == "TOT"
    is_itx_category = invoice_type == "ITX"

    applied_tax_category = data.get("tax_category")
    if is_lpo_category:
                applied_tax_category = "LPO"
                lpo_tax_template = get_lpo_tax_template(company)
                print("🚀 ~ create_sales_invoice ~ lpo_tax_template:", lpo_tax_template)

    if is_tot_category:
        applied_tax_category = "TOT"
        sales_tax_template = None
    elif is_itx_category:
        applied_tax_category = "ITX"
        sales_tax_template = None
    else:
        sales_tax_template = data.get("salesTaxTemplate")

    invoice.update(
        {
            "customer": data.get("customerId"),
            "currency": currency,
            "conversion_rate": data.get("exchangeRate", 1),
            "posting_date": data.get("postingDate"),
            "due_date": data.get("dueDate"),
            "tax_category": applied_tax_category,
            "update_stock": 1 if data.get("updateStock") else 0,
            "set_posting_time": 1,
            "set_warehouse": data.get("warehouse"),
            "customer_address": data.get("billingAddress"),
            "shipping_address_name": data.get("shippingAddress"),
            "taxes_and_charges": sales_tax_template,
            "cost_center": cost_center,
            "debit_to": account,
            "additional_discount_percentage": data.get("additional_discount_percentage"),
            "discount_amount": data.get("discount_amount"),
            "po_no": data.get("lpoNumber"),
        }
    )

    for item in data.get("items", []):
        item_code = item.get("itemCode")
        batch_no = item.get("batchNo") or item.get("batch_no")
        mfg_date = item.get("mfgDate") or item.get("mfg_date")
        exp_date = item.get("expDate") or item.get("exp_date")
        print("🚀 ~ create_sales_invoice ~ original tax:", _get_item_tax_template(item_code, data.get("tax_category")))

        if batch_no:
            ensure_batch(item_code, batch_no, mfg_date, exp_date)

        if is_lpo_category:
            applied_tax_template = lpo_tax_template
        elif is_tot_category:
            applied_tax_template = None
        elif is_itx_category:
            applied_tax_template = None
        else:
            applied_tax_template = _get_item_tax_template(item_code, data.get("tax_category"))
        print("🚀 ~ create_sales_invoice ~ applied_tax_template:", applied_tax_template)
        invoice.append(
            "items",
            {
                "item_code": item_code,
                "qty": item.get("quantity"),
                "warehouse": item.get("warehouse", data.get("warehouse")),
                "batch_no": batch_no,
                "item_tax_template": applied_tax_template,
                "discount_percentage": item.get("discount", 0),
                "price_list_rate": item.get("rate"),
                "description": item.get("description", None),
            },
        )

        invoice.append("custom_item_box_detail", _build_sales_invoice_box_detail(item))

    additional_details = _build_additional_detail(data)
    if additional_details:
        invoice.append("custom_details", additional_details)

    sync_taxes(invoice, data)

    # for i, row in enumerate(invoice.items):
    #     print(f"🚀 ~ BEFORE INSERT ~ Row {i}: {row.item_tax_template}")
    try:
        invoice.insert(ignore_permissions=True)
        # for i, row in enumerate(invoice.items):
        #     print(f"🚀 ~ AFTER INSERT ~ Row {i}: {row.item_tax_template}")
    except frappe.ValidationError as e:
        error_msg = str(e)
        if "Due Date cannot be after" in error_msg:
            allowed_date = error_msg.replace("Due Date cannot be after ", "").strip()
            frappe.throw(
                f"The due date cannot be later than {allowed_date} based on the invoice payment term. "
                "Please update the payment term to change the due date."
            )
        raise e

    terms_payload = data.get("terms")
    if terms_payload:
        sync_invoice_terms(invoice, terms_payload)

    return invoice

def update_sales_invoice_customer(invoice, customer_id):

    if not customer_id or customer_id == invoice.customer:
        return

    invoice.customer = customer_id

    # Contact
    invoice.contact_person = None
    invoice.contact_display = None
    invoice.contact_email = None
    invoice.contact_mobile = None
    invoice.contact_phone = None

    # Billing Address
    invoice.customer_address = None
    invoice.address_display = None

    # Shipping Address
    invoice.shipping_address_name = None
    invoice.shipping_address = None

    # Refresh customer defaults
    invoice.set_missing_values()
    
def update_sales_invoice(invoice_id, data):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    if invoice.docstatus == 1:
        raise frappe.ValidationError(
            "Cannot edit a submitted Sales Invoice. Cancel it first."
        )

    company = invoice.company
    company_doc = frappe.get_cached_doc("Company", company)

    currency = data.get("currency") or company_doc.default_currency
    cost_center = (
        data.get("costCenter") or invoice.cost_center or company_doc.cost_center
    )

    update_sales_invoice_customer(invoice, data.get("customerId"))

    existing_invoice_type = (
        invoice.custom_details[0].invoice_type
        if invoice.get("custom_details") and len(invoice.custom_details) > 0
        else None
    )
    effective_invoice_type = data.get("invoiceType", existing_invoice_type)
    is_lpo_category = effective_invoice_type == "LPO"
    is_tot_category = effective_invoice_type == "TOT"
    is_itx_category = effective_invoice_type == "ITX"

    field_map = {
        "currency": "currency",
        "exchangeRate": "conversion_rate",
        "postingDate": "posting_date",
        "dueDate": "due_date",
        "tax_category": "tax_category",
        "warehouse": "set_warehouse",
        "billingAddress": "customer_address",
        "shippingAddress": "shipping_address_name",
        "salesTaxTemplate": "taxes_and_charges",
        "lpoNumber": "po_no"
    }

    for api_field, doc_field in field_map.items():
        if data.get(api_field) is not None:
            setattr(invoice, doc_field, data.get(api_field))

    if currency:
        invoice.currency = currency

    if cost_center:
        invoice.cost_center = cost_center

    if data.get("updateStock") is not None:
        invoice.update_stock = 1 if data.get("updateStock") else 0
        invoice.set_posting_time = 1


    if is_lpo_category:
        invoice.tax_category = "LPO"
        lpo_tax_template = get_lpo_tax_template(company)
    elif is_tot_category:
        invoice.tax_category = "TOT"
        invoice.taxes_and_charges = None
    elif is_itx_category:
        invoice.tax_category = "ITX"
        invoice.taxes_and_charges = None

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

            if is_lpo_category:
                applied_tax_template = lpo_tax_template
            elif is_tot_category or is_itx_category:
                applied_tax_template = None
            else:
                applied_tax_template = _get_item_tax_template(
                    item_code,
                    data.get("tax_category") or invoice.tax_category,
                )

            invoice.append(
                "items",
                {
                    "item_code": item_code,
                    "qty": item.get("quantity"),
                    "price_list_rate": item.get("rate"),
                    "warehouse": item.get("warehouse", invoice.set_warehouse),
                    "batch_no": batch_no,
                    "item_tax_template": applied_tax_template,
                    "discount_percentage": item.get("discount", 0),
                    "description": item.get("description"),
                },
            )

            invoice.append(
                "custom_item_box_detail",
                _build_sales_invoice_box_detail(item),
            )

    sync_taxes(invoice, data)

    if any(k in data for k in ["paymentMode", "payment_mode", "invoiceType", "principal", "principalDetails", "principal_details"]):
        detail = _build_additional_detail(data)
        invoice.set("custom_details", [])
        if detail:
            invoice.append("custom_details", detail)

    invoice.additional_discount_percentage = data.get("additional_discount_percentage")
    invoice.discount_amount = data.get("discount_amount")
    invoice.save(ignore_permissions=True)

    terms_payload = data.get("terms")
    if terms_payload:
        sync_invoice_terms(invoice, terms_payload)

    return invoice

def get_sales_invoice_by_id(invoice_id, is_credit_note=False, is_sales_debit_note=False):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    customer = frappe.get_doc("Customer", invoice.customer)

    box_details = invoice.get("custom_item_box_detail", [])
    custom_details = invoice.get("custom_details", [])
    acount_details = frappe.db.get_value(
        "Account",
        invoice.debit_to,
        ["account_name", "account_number", "account_currency"],
        as_dict=True,
    )
    gl_account_name = (
        f"{acount_details.get('account_number', '')} - {acount_details.get('account_name', '')}"
        if acount_details.get("account_number")
        else acount_details.get("account_name")
    )
    data = {
        "id": invoice.name,
        "customerId": invoice.customer,
        "customerName": customer.customer_name,
        "customerTpin": customer.tax_id,
        "customerContactNo": customer.mobile_no,
        "currency": invoice.currency,
        "exchangeRate": invoice.conversion_rate,
        "postingDate": invoice.posting_date,
        "dueDate": invoice.due_date,
        "tax_category": invoice.tax_category,
        "updateStock": bool(invoice.update_stock),
        "warehouse": invoice.set_warehouse,
        "customerAddressId": invoice.customer_address,
        "billingAddress": invoice.address_display,
        "shippingAddressId": invoice.shipping_address_name,
        "shippingAddress": invoice.shipping_address,
        "salesTaxTemplate": invoice.taxes_and_charges,
        "status": invoice.status,
        "docstatus": invoice.docstatus,
        "outstanding_amount": invoice.outstanding_amount,
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
        "contact_email": invoice.contact_email,
        "gl_account": invoice.debit_to,
        "gl_account_name": gl_account_name,
        "gl_account_currency": (
            acount_details.get("account_currency") if acount_details else None
        ),
        "remarks": invoice.remarks,
        "additional_discount_percentage": invoice.additional_discount_percentage,
        "discount_amount": invoice.discount_amount,
        "lpoNumber":invoice.po_no
    }

    payment_mode = custom_details[0].payment_mode if custom_details else None
    reason = custom_details[0].reason if custom_details else None
    invoice_type = custom_details[0].invoice_type if custom_details else None
    principal_detail = json.dumps(custom_details[0].zra_principal_detail if custom_details else None)

    data["paymentInformation"] = get_payment_information(payment_mode, invoice.company)
    data["paymentMode"] = custom_details[0].payment_mode if custom_details else None
    data["reason"] = reason
    data["invoiceType"] = invoice_type
    data["principal"] = principal_detail

    is_cn = str(is_credit_note).lower() in ("true", "1") if isinstance(is_credit_note, (str, int)) else bool(is_credit_note)
    is_dn = str(is_sales_debit_note).lower() in ("true", "1") if isinstance(is_sales_debit_note, (str, int)) else bool(is_sales_debit_note)
    is_return_or_debit = is_cn or is_dn
    credited_map = get_already_credited_qty(invoice_id) if is_return_or_debit else {}

    for item in invoice.items:
        tax = _get_tax(item.item_code, invoice.tax_category)
        remaining_qty = item.qty
        if is_return_or_debit:
            key = (item.item_code, item.batch_no or "")
            credited_qty = credited_map.get(key, 0)
            remaining_qty = item.qty - credited_qty

            if remaining_qty <= 0:
                continue  # fully credited or adjusted already — skip this item entirely

        item_data = {
            "itemCode": item.item_code,
            "itemName": item.item_name,
            "brand": item.brand,
            "uom": item.uom,
            "quantity": remaining_qty,
            "rate": item.price_list_rate,
            "warehouse": item.warehouse,
            "batchNo": item.batch_no,
            "costCenter": item.cost_center,
            "itemTaxTemplate": item.item_tax_template,
            "taxInfo": tax,
            "discount": item.discount_percentage,
            "discount_amount": item.discount_amount,
            "description": item.description,
            "conversion_factor": item.conversion_factor,
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
                    "isServiceItem": bool(
                        frappe.db.exists(
                            "Item",
                            {
                                "name": item.item_code,
                                "is_stock_item": 0,
                                "is_sales_item": 1,
                                "disabled": 0,
                            },
                        )
                    ),
                }
            )

        data["items"].append(item_data)
    total_tax = 0
    total_charges = 0

    for tax in invoice.get("taxes", []):
        amount = tax.tax_amount or 0

        account = frappe.get_cached_value(
            "Account",
            tax.account_head,
            ["account_type", "account_name"],
            as_dict=True,
        )

        account_type = account.account_type if account else None
        account_name = account.account_name if account else None

        if account_type == "Tax":
            row = {
                "accountHead": tax.account_head,
                "accountName": account_name,
                "rate": tax.rate,
                "amount": amount,
                "description": tax.description,
            }
            data["taxes"].append(row)
            total_tax += amount

        else:
            row = {
                "accountHead": tax.account_head,
                "accountName": account_name,
                "rate": tax.rate,
                "amount": amount,
                "description": tax.description,
            }
            data["charges"].append(row)
            total_charges += amount

    data["totalCalculatedTax"] = total_tax
    data["totalCalculatedCharges"] = total_charges

    if invoice.tc_name and frappe.db.exists("Terms and Conditions", invoice.tc_name):
        tc_content = frappe.db.get_value(
            "Terms and Conditions", invoice.tc_name, "terms"
        )
        try:
            data["terms"]["selling"] = json.loads(tc_content)
        except Exception:
            data["terms"]["selling"] = tc_content

    attachments = frappe.db.get_all(
        "File",
        filters={
            "attached_to_doctype": "Sales Invoice",
            "attached_to_name": invoice_id,
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
    order_by = "creation desc"
    if filters.get("sortBy"):
        order_by = f"{filters.get('sortBy')} {filters.get('sortOrder') or 'asc'}"

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
            "debit_to",
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by=order_by,
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
        account_details = frappe.db.get_value(
            "Account", inv.debit_to, ["account_name", "account_number"], as_dict=True
        )

        inv["gl_account_name"] = (
            f"{account_details.get('account_number', '')} - {account_details.get('account_name', '')}"
            if account_details.get("account_number")
            else account_details.get("account_name")
        )
        inv["gl_account"] = inv.pop("debit_to")
        inv["id"] = inv.pop("name")
        inv["customerId"] = inv.pop("customer")
        inv["customerName"] = inv.pop("customer_name")
        inv["invoiceDate"] = inv.pop("posting_date")
        inv["dueDate"] = inv.pop("due_date")
        inv["total"] = inv.pop("grand_total")
        inv["baseGrandTotal"] = inv.pop("base_grand_total")
        inv["exchangeRate"] = inv.pop("conversion_rate")
        inv["baseOutstandingAmount"] = (
            inv["outstanding_amount"] * inv["exchangeRate"]
            if inv["exchangeRate"]
            else inv["outstanding_amount"]
        )
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


def validate_strict_credit_limit(invoice):
    customer = frappe.get_doc("Customer", invoice.customer)
    
    credit_limit = 0.0
    strict_policy = 0
    bypass_at_sales_order = 0

    for limit in customer.get("credit_limits", []):
        if limit.company == invoice.company:
            credit_limit = float(limit.credit_limit or 0.0)
            bypass_at_sales_order = cint(limit.get("bypass_credit_limit_check_at_sales_order", 0))
            break

    if customer.get("custom_extended_details") and len(customer.custom_extended_details) > 0:
        strict_policy = cint(customer.custom_extended_details[0].get("strict_credit_limit", 0))

    if strict_policy and credit_limit > 0:
        
        outstanding = get_customer_outstanding(
            invoice.customer, 
            invoice.company,
            ignore_outstanding_sales_order=bypass_at_sales_order
        )
        
        total_exposure = outstanding + invoice.base_grand_total

        if total_exposure > credit_limit:
            frappe.throw(
                f"<b>Strict Credit Limit Enforced:</b> Cannot approve invoice '{invoice.name}'.<br><br>"
                f"Customer <b>'{invoice.customer_name}'</b> has exceeded their strict credit limit of {credit_limit:,.2f}. "
                f"Current exposure (including this invoice) is {total_exposure:,.2f}.<br><br>"
                "Exceptions and role-based overrides are strictly prohibited for this customer.",
                title="Strict Credit Limit Exceeded"
            )


def process_approval(invoice):
    if invoice.docstatus == 1:
        raise frappe.ValidationError("Invoice is already approved.")
    if invoice.docstatus == 2:
        raise frappe.ValidationError("Cannot approve a cancelled invoice. Please amend it first.")

    validate_strict_credit_limit(invoice)

    if invoice.get("custom_details") and len(invoice.custom_details) > 0:
        invoice.custom_details[0].approved_by = frappe.session.user
        invoice.custom_details[0].approved_at = now()
    else:
        invoice.append(
            "custom_details",
            {"approved_by": frappe.session.user, "approved_at": now()},
        )

    try:
        invoice.submit()
    except frappe.ValidationError as e:
        message = str(e)
        if "Credit limit has been crossed for customer" in message:
            match = re.search(r"\(([\d.]+)/([\d.]+)\)", message)
            outstanding = float(match.group(1)) if match else 0
            credit_limit = float(match.group(2)) if match else 0

            contact_users = ""
            user_match = re.search(r"Please contact any of the following users.*?: (.+)", message)
            if user_match:
                contact_users = user_match.group(1)

            raise frappe.ValidationError(
                f"Unable to approve invoice '{invoice.name}' because customer '{invoice.customer_name}' "
                f"has exceeded their credit limit. "
                f"Current outstanding amount: {outstanding:,.2f}. "
                f"Credit limit: {credit_limit:,.2f}. "
                "Please either reduce the invoice amount, increase the customer's credit limit, "
                "or contact an authorized user to approve a credit limit exception. "
                f"Contact users: {contact_users}"
            )
        raise

    return {
        "id": invoice.name,
        "status": invoice.status,
        "docstatus": invoice.docstatus,
        "approved_by": invoice.custom_details[0].approved_by if invoice.get("custom_details") else None,
        "approved_at": invoice.custom_details[0].approved_at if invoice.get("custom_details") else None,
    }


def process_cancellation(invoice):
    if invoice.docstatus == 2:
        raise frappe.ValidationError("Invoice is already cancelled.")
    if invoice.docstatus == 0:
        raise frappe.ValidationError("Cannot cancel a Draft invoice. Submit it first.")

    if invoice.get("custom_details") and len(invoice.custom_details) > 0:
        invoice.custom_details[0].cancelled_by = frappe.session.user
        invoice.custom_details[0].cancelled_at = now()
    else:
        invoice.append(
            "custom_details",
            {"cancelled_by": frappe.session.user, "cancelled_at": now()},
        )

    invoice.cancel()

    return {
        "id": invoice.name,
        "status": invoice.status,
        "docstatus": invoice.docstatus,
        "cancelled_by": invoice.custom_details[0].cancelled_by if invoice.get("custom_details") else None,
        "cancelled_at": invoice.custom_details[0].cancelled_at if invoice.get("custom_details") else None,
    }


def process_amendment(invoice):
    if invoice.docstatus == 0:
        raise frappe.ValidationError("Invoice is already in Draft state.")
    if invoice.docstatus == 1:
        raise frappe.ValidationError("Cannot amend an approved invoice. Cancel it first.")

    amended_doc = frappe.copy_doc(invoice)
    amended_doc.amended_from = invoice.name
    amended_doc.docstatus = 0

    if amended_doc.get("custom_details"):
        for row in amended_doc.custom_details:
            row.approved_by = None
            row.approved_at = None
            row.cancelled_by = None
            row.cancelled_at = None

    amended_doc.insert()

    return {
        "id": amended_doc.name,
        "status": amended_doc.status,
        "docstatus": amended_doc.docstatus,
    }

def update_sales_invoice_status(invoice_id, action):

    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    if not frappe.has_permission("Sales Invoice", "write", invoice):
        raise frappe.PermissionError("No permission to modify this invoice")

    if action == "approved":
        return process_approval(invoice)
        
    elif action == "cancelled":
        return process_cancellation(invoice)
        
    elif action == "amend":
        return process_amendment(invoice)
        
    else:
        raise frappe.ValidationError("Invalid action. Allowed: approved, cancelled, amend")