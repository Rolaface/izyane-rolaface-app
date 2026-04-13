import json
import frappe
from frappe.utils import flt, cint, add_days

def sync_invoice_terms(invoice, terms_payload):
    terms_data = terms_payload.get("Selling") or terms_payload.get("selling")
    if not terms_data:
        return

    is_invoice_dirty = False

    pt_name = f"{invoice.name} PT"
    phases = terms_data.get("payment", {}).get("phases", [])
    
    if phases:
        if not frappe.db.exists("Payment Terms Template", pt_name):
            pt_doc = frappe.get_doc({
                "doctype": "Payment Terms Template",
                "template_name": pt_name
            })
        else:
            pt_doc = frappe.get_doc("Payment Terms Template", pt_name)
            pt_doc.set("terms", [])

        total_pct = 0.0
        for phase in phases:
            term_name = phase.get("name")
            pct = flt(phase.get("percentage"))
            credit_days = cint(phase.get("credit_days", 0))
            total_pct += pct

            if not term_name:
                continue

            if not frappe.db.exists("Payment Term", term_name):
                frappe.get_doc({
                    "doctype": "Payment Term",
                    "payment_term_name": term_name,
                    "description": phase.get("condition", ""),
                    "invoice_portion": pct,
                    "due_date_based_on": "Day(s) after invoice date",
                    "credit_days": credit_days
                }).insert(ignore_permissions=True)
            else:
                pt = frappe.get_doc("Payment Term", term_name)
                pt.description = phase.get("condition", "")
                pt.invoice_portion = pct
                pt.credit_days = credit_days
                pt.save(ignore_permissions=True)

            pt_doc.append("terms", {
                "payment_term": term_name,
                "invoice_portion": pct,
                "credit_days": credit_days
            })

        if round(total_pct, 2) == 100.00:
            pt_doc.save(ignore_permissions=True)
            
            invoice.payment_terms_template = pt_doc.name
            invoice.set("payment_schedule", [])
            
            base_date = invoice.posting_date or frappe.utils.today()
            
            for phase in phases:
                credit_days = cint(phase.get("credit_days", 0))
                calculated_due_date = add_days(base_date, credit_days)
                
                invoice.append("payment_schedule", {
                    "payment_term": phase.get("name"),
                    "description": phase.get("condition", ""),
                    "invoice_portion": flt(phase.get("percentage")),
                    "due_date": calculated_due_date
                })
            is_invoice_dirty = True
        else:
            raise frappe.ValidationError(f"Payment phases must sum to exactly 100%. Current sum: {round(total_pct, 2)}%")

    tc_name = f"{invoice.name} Terms"
    tc_content = json.dumps(terms_data, indent=2)

    if frappe.db.exists("Terms and Conditions", tc_name):
        tc_doc = frappe.get_doc("Terms and Conditions", tc_name)
        tc_doc.terms = tc_content
        tc_doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({
            "doctype": "Terms and Conditions",
            "title": tc_name,
            "terms": tc_content,
            "selling": 1
        }).insert(ignore_permissions=True)

    invoice.tc_name = tc_name
    invoice.terms = tc_content 
    is_invoice_dirty = True

    notes = terms_data.get("payment", {}).get("notes")
    if notes:
        invoice.remarks = notes
        is_invoice_dirty = True

    if is_invoice_dirty:
        invoice.save(ignore_permissions=True)

def sync_taxes(invoice, data):
    template_name = data.get("salesTaxTemplate")
    tax_overrides = data.get("taxes", [])
    
    is_dirty = False
    override_map = {t.get("accountHead"): t for t in tax_overrides if t.get("accountHead")}

    if template_name and frappe.db.exists("Sales Taxes and Charges Template", template_name):
        template = frappe.get_doc("Sales Taxes and Charges Template", template_name)
        existing_heads = [t.account_head for t in invoice.get("taxes", [])]
        
        for t_row in template.taxes:
            if t_row.account_head not in existing_heads:
                invoice.append("taxes", {
                    "charge_type": t_row.charge_type,
                    "account_head": t_row.account_head,
                    "description": t_row.description,
                    "cost_center": t_row.cost_center,
                    "rate": t_row.rate,
                    "tax_amount": t_row.tax_amount
                })
                is_dirty = True

    for tax_row in invoice.get("taxes", []):
        override = override_map.get(tax_row.account_head)
        if override:
            if "amount" in override and override["amount"] is not None:
                tax_row.charge_type = "Actual" 
                tax_row.rate = 0
                tax_row.tax_amount = flt(override["amount"])
                is_dirty = True
            elif "rate" in override and override["rate"] is not None:
                if tax_row.charge_type == "Actual":
                    tax_row.charge_type = "On Net Total" 
                tax_row.rate = flt(override["rate"])
                tax_row.tax_amount = 0
                is_dirty = True
                
    return is_dirty

def create_sales_invoice(data):
    doc_args = {
        "doctype": "Sales Invoice",
        "customer": data.get("customerId"),
        "currency": data.get("currency", "INR"),
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
        "items": []
    }

    for item in data.get("items", []):
        doc_args["items"].append({
            "item_code": item.get("itemCode"),
            "qty": item.get("quantity"),
            "rate": item.get("rate"),
            "warehouse": item.get("warehouse", data.get("warehouse")),
            "batch_no": item.get("batchNo") or item.get("batch_no"),
            "item_tax_template": item.get("itemTaxTemplate")
        })

    invoice = frappe.get_doc(doc_args).insert(ignore_permissions=True)
    needs_save = False

    if sync_taxes(invoice, data):
        needs_save = True

    terms_payload = data.get("terms")
    if terms_payload:
        sync_invoice_terms(invoice, terms_payload)
    elif needs_save:
        invoice.save(ignore_permissions=True)

    return invoice

def update_sales_invoice(invoice_id, data):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    if invoice.docstatus == 1:
        raise frappe.ValidationError("Cannot edit a submitted Sales Invoice. Cancel it first.")

    field_map = {
        "customerId": "customer", "currency": "currency", "exchangeRate": "conversion_rate",
        "postingDate": "posting_date", "dueDate": "due_date", "tax_category": "tax_category",
        "warehouse": "set_warehouse", "billingAddress": "customer_address", 
        "shippingAddress": "shipping_address_name", "salesTaxTemplate": "taxes_and_charges"
    }

    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(invoice, v, data.get(k))

    if data.get("updateStock") is not None:
        invoice.update_stock = 1 if data.get("updateStock") else 0
        invoice.set_posting_time = 1 if data.get("updateStock") else 0

    if "items" in data:
        invoice.set("items", [])
        for item in data.get("items"):
            invoice.append("items", {
                "item_code": item.get("itemCode"),
                "qty": item.get("quantity"),
                "rate": item.get("rate"),
                "warehouse": item.get("warehouse", invoice.set_warehouse),
                "batch_no": item.get("batchNo") or item.get("batch_no"),
                "item_tax_template": item.get("itemTaxTemplate")
            })

    sync_taxes(invoice, data)
    invoice.save(ignore_permissions=True)

    terms_payload = data.get("terms")
    if terms_payload:
        sync_invoice_terms(invoice, terms_payload)

    return invoice

def get_sales_invoice_by_id(invoice_id):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)

    data = {
        "id": invoice.name,
        "customerId": invoice.customer,
        "currency": invoice.currency,
        "exchangeRate": invoice.conversion_rate,
        "postingDate": invoice.posting_date,
        "dueDate": invoice.due_date,
        "tax_category": invoice.tax_category,
        "updateStock": bool(invoice.update_stock),
        "warehouse": invoice.set_warehouse,
        "billingAddress": invoice.customer_address,
        "shippingAddress": invoice.shipping_address_name,
        "salesTaxTemplate": invoice.taxes_and_charges,
        "status": invoice.status,
        "docstatus": invoice.docstatus,
        "items": [],
        "taxes": [],
        "terms": {}
    }

    for item in invoice.items:
        data["items"].append({
            "itemCode": item.item_code,
            "quantity": item.qty,
            "rate": item.rate,
            "warehouse": item.warehouse,
            "batch_no": item.get("batchNo") or item.get("batch_no"),
            "itemTaxTemplate": item.item_tax_template
        })

    for tax in invoice.get("taxes", []):
        data["taxes"].append({
            "accountHead": tax.account_head,
            "rate": tax.rate,
            "amount": tax.tax_amount
        })

    if invoice.tc_name and frappe.db.exists("Terms and Conditions", invoice.tc_name):
        tc_content = frappe.db.get_value("Terms and Conditions", invoice.tc_name, "terms")
        try:
            data["terms"]["Selling"] = json.loads(tc_content)
        except Exception:
            data["terms"]["Selling"] = tc_content

    return data

def get_sales_invoices(page, page_size):
    start = (page - 1) * page_size
    total_invoices = frappe.db.count("Sales Invoice")
    total_pages = (total_invoices + page_size - 1) // page_size

    invoices = frappe.get_all(
        "Sales Invoice",
        fields=["name", "customer", "customer_name", "posting_date", "due_date", "base_grand_total", "currency", "conversion_rate", "outstanding_amount", "tax_category","status"],
        limit_start=start, limit_page_length=page_size, order_by="creation desc"
    )

    for inv in invoices:
        inv["id"] = inv.pop("name")
        inv["customerId"] = inv.pop("customer")
        inv["customerName"] = inv.pop("customer_name")
        inv["invoiceDate"] = inv.pop("posting_date")
        inv["dueDate"] = inv.pop("due_date")
        inv["total"] = inv.pop("base_grand_total")
        inv["currency"] = inv.pop("currency")
        inv["exchangeRate"] = inv.pop("conversion_rate")
        inv["outstandingAmount"] = inv.pop("outstanding_amount")
        inv["status"] = inv.pop("status")
        inv["taxCategory"] = inv.pop("tax_category")

    return invoices, total_invoices, total_pages

def delete_sales_invoice(invoice_id):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    if invoice.docstatus == 1:
        raise frappe.ValidationError("Cannot delete a submitted Sales Invoice. Cancel it first.")
    
    frappe.db.set_value("Sales Invoice", invoice_id, {
        "tc_name": None,
        "payment_terms_template": None
    }, update_modified=False)
    
    frappe.delete_doc("Sales Invoice", invoice_id, ignore_permissions=True)

    tc_name = f"{invoice_id} Terms"
    pt_name = f"{invoice_id} PT"

    if frappe.db.exists("Terms and Conditions", tc_name):
        frappe.delete_doc("Terms and Conditions", tc_name, ignore_permissions=True, force=True)

    if frappe.db.exists("Payment Terms Template", pt_name):
        template_doc = frappe.get_doc("Payment Terms Template", pt_name)
        terms_to_delete = [t.payment_term for t in template_doc.terms]
        
        frappe.delete_doc("Payment Terms Template", pt_name, ignore_permissions=True, force=True)
        
        for term in terms_to_delete:
            try:
                frappe.delete_doc("Payment Term", term, ignore_permissions=True, force=True)
            except frappe.exceptions.LinkExistsError:
                pass

def update_sales_invoice_status(invoice_id, action):
    invoice = frappe.get_doc("Sales Invoice", invoice_id)
    
    if action == "submit":
        if invoice.docstatus == 1:
            raise frappe.ValidationError("Invoice is already submitted.")
        invoice.submit()
    elif action == "cancel":
        if invoice.docstatus == 2:
            raise frappe.ValidationError("Invoice is already cancelled.")
        if invoice.docstatus == 0:
            raise frappe.ValidationError("Cannot cancel a Draft invoice. Delete it instead.")
        invoice.cancel()
        
    return invoice.status