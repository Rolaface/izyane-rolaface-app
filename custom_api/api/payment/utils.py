import frappe
from datetime import datetime
from frappe.utils import flt
from .constant import LEDGER_ACCOUNT_TYPE_MAP

class PaymentEntryError(Exception):

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code

def validate_required(data, fields):
    for field in fields:
        if not data.get(field):
            return field
    return None

def get_required_field_labels(payment_type):
    if payment_type == "Internal Transfer":
        return {
                "paid_from": "Paid From Account",
                "paid_to": "Paid To Account",
               }
    return {
            "payment_type": "Payment Type",
            "party_type": "Party Type",
            "party_id": "Party",
            "mode_of_payment": "Mode of Payment",
            "payment_date": "Payment Date",
            "paid_from": "Paid From Account",
            "paid_to": "Paid To Account",
            "paid_from_amount": "Amount",
            "reference_no": "Reference Number",
            "reference_date": "Reference Date",
          }

def resolve_party_name(party_type, party_id):
    doctype_map = {
        "Customer": ("Customer", "custom_id"),
        "Supplier": ("Supplier", "custom_id"),
        "Employee": ("Employee", "name"),
        "Shareholder": ("Shareholder", "custom_id"),
    }
    doctype, id_field = doctype_map.get(party_type, (None, None))
    if not doctype:
        return None
    return frappe.db.get_value(doctype, {id_field: party_id}, "name")

def resolve_exchange_rates(paid_from_currency, paid_to_currency, company_currency, payment_date, exchange_rate):
    from erpnext.setup.utils import get_exchange_rate

    if (paid_from_currency == paid_to_currency) and (paid_from_currency != company_currency):
        source_exchange_rate = target_exchange_rate = get_exchange_rate(
            from_currency=paid_from_currency,
            to_currency=company_currency,
            transaction_date=payment_date,
        )

        if source_exchange_rate < 1:
            frappe.throw(
                f"""Unable to find exchange rate for {paid_from_currency} to {paid_to_currency} for key date {payment_date}.
                                  Please create a Currency Exchange record manually"""
            )
        return source_exchange_rate, target_exchange_rate

    source_exchange_rate = 1.0 if paid_from_currency == company_currency else exchange_rate
    target_exchange_rate = 1.0 if paid_to_currency == company_currency else exchange_rate
    return source_exchange_rate, target_exchange_rate

def build_references(references, pe):
    pe.set("references", [])

    reference_exchange_rate = (
        pe.source_exchange_rate if pe.payment_type == "Receive" else pe.target_exchange_rate
    )

    for ref in references:
        reference_doctype = ref.get("reference_doctype")
        reference_name = ref.get("reference_name")
        allocated_amount = float(ref.get("allocated_amount") or 0)

        if not reference_doctype or not reference_name:
            continue

        if reference_doctype == "Purchase Order":
            outstanding = frappe.db.get_value(reference_doctype, reference_name, "grand_total") or 0
            total_amount = frappe.db.get_value(reference_doctype, reference_name, "base_grand_total") or 0

        elif reference_doctype == "Expense Claim":
            claim = frappe.get_doc("Expense Claim", reference_name)
            precision = frappe.get_precision("Expense Claim", "grand_total")

            total_amount = flt(claim.total_sanctioned_amount + claim.total_taxes_and_charges, precision)
            outstanding = flt(claim.grand_total - claim.total_amount_reimbursed, precision)

        elif reference_doctype == "Employee Advance":
            advance = frappe.get_doc("Employee Advance", reference_name)
            if advance.docstatus != 1:
                frappe.throw(f"Employee Advance {reference_name} is not submitted.")
            paid_amount = advance.advance_amount

            total_amount = paid_amount
            outstanding = total_amount

        else:
            outstanding = frappe.db.get_value(reference_doctype, reference_name, "outstanding_amount") or 0
            total_amount = frappe.db.get_value(reference_doctype, reference_name, "grand_total") or 0

        pe.append("references", {
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "total_amount": total_amount,
            "outstanding_amount": outstanding,
            "allocated_amount": allocated_amount,
            "exchange_rate": reference_exchange_rate,
        })

def build_taxes(taxes, pe):
    pe.set("taxes", [])
    for tax in taxes:
        pe.append("taxes", {
            "charge_type": tax.get("type", "Actual"),
            "account_head": tax.get("account_head"),
            "rate": float(tax.get("tax_rate") or 0),
            "tax_amount": float(tax.get("amount") or 0),
            "total": float(tax.get("total") or 0),
            "description": tax.get("account_head"),
        })

def build_deduction(deductions, pe):
    pe.set("deductions", [])
    for deduction in deductions:
        pe.append("deductions", {
            "account": deduction.get("account"),
            "cost_center": deduction.get("cost_center"),
            "amount": float(deduction.get("amount") or 0),
        })

def mark_reference_pdc_used(reference_no):
    if not reference_no:
        return

    pdc = frappe.db.get_value(
        "Custom Pdc Details",
        {"cheque_reference_number": reference_no, "status": "Unused"},
        ["name", "document_type", "document_name"],
        as_dict=True,
    )
    if pdc:
        frappe.db.set_value("Custom Pdc Details", pdc.name, "status", "Used")
        if pdc.document_type and pdc.document_name:
            from frappe.desk.doctype.tag.tag import remove_tag
            remove_tag("PDC", pdc.document_type, pdc.document_name)

def build_payment_entry_response(pe):
    return {
        "paymentId": pe.name,
        "paymentType": pe.payment_type,
        "partyType": pe.party_type,
        "partyName": pe.party,
        "paidFrom": pe.paid_from,
        "paidTo": pe.paid_to,
        "paidAmount": pe.paid_amount,
        "receivedAmount": pe.received_amount,
        "paymentDate": str(pe.posting_date),
        "referenceNo": pe.reference_no,
        "status": pe.status,
    }

def build_ledger_account_filters(payment_type, filter_param, party_type, company):
    # In case of Internal Transfer, party_type = payment_type. This keeps that flow intact.
    if payment_type == "Internal Transfer":
        party_type = "Internal Transfer"

    party_map = LEDGER_ACCOUNT_TYPE_MAP.get(party_type, LEDGER_ACCOUNT_TYPE_MAP["Customer"])

    # Pay:     money goes OUT → "from" = Bank/Cash, "to" = Payable/Receivable
    # Receive: money comes IN → "from" = Payable/Receivable, "to" = Bank/Cash
    if payment_type == "Receive":
        resolved_filter = "to" if filter_param == "from" else "from"
    else:
        resolved_filter = filter_param

    account_types = party_map.get(resolved_filter, ["Bank", "Cash"])

    return {
        "account_type": ["in", account_types],
        "is_group": 0,
        "company": company,
    }

def build_payment_list_query(args):
    filters = {}
    or_filters = []

    payment_type = args.get("paymentType")
    if payment_type:
        payment_type = payment_type.lower()
        if payment_type == "receive":
            filters["payment_type"] = "Receive"
        elif payment_type == "pay":
            filters["payment_type"] = "Pay"

    party_type = args.get("partyType")
    if party_type:
        filters["party_type"] = party_type

    party_name_query = args.get("partyName")
    if party_name_query and party_type:
        if party_type == "Customer":
            party_name = frappe.db.get_value("Customer", {"customer_name": party_name_query}, "name")
        elif party_type == "Supplier":
            party_name = frappe.db.get_value("Supplier", {"supplier_name": party_name_query}, "name")
        else:
            party_name = None

        if not party_name:
            raise PaymentEntryError(f"{party_type} with ID '{party_name_query}' not found.", 404)

        filters["party_type"] = party_type
        filters["party"] = party_name

    payment_mode = args.get("paymentMode")
    if payment_mode:
        filters["mode_of_payment"] = ["like", f"%{payment_mode}%"]

    status = args.get("status")
    if status:
        filters["status"] = ["in", status.split(",")]

    from_date = args.get("fromDate")
    to_date = args.get("toDate")
    if from_date and to_date:
        filters["posting_date"] = ["between", [from_date, to_date]]
    elif from_date:
        filters["posting_date"] = [">=", from_date]
    elif to_date:
        filters["posting_date"] = ["<=", to_date]

    min_amount = args.get("minAmount")
    max_amount = args.get("maxAmount")
    if min_amount and max_amount:
        filters["paid_amount"] = ["between", [float(min_amount), float(max_amount)]]
    elif min_amount:
        filters["paid_amount"] = [">=", float(min_amount)]
    elif max_amount:
        filters["paid_amount"] = ["<=", float(max_amount)]

    search = args.get("search")
    if search:
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["party", "like", f"%{search}%"],
            ["mode_of_payment", "like", f"%{search}%"],
            ["reference_no", "like", f"%{search}%"],
            ["party_type", "like", f"%{search}%"],
            ["payment_type", "like", f"%{search}%"],
            ["company", "like", f"%{search}%"],
            ["party_name", "like", f"%{search}%"],
        ]

        try:
            search_amount = float(search)
            or_filters.append(["paid_amount", "=", search_amount])
        except ValueError:
            pass

        try:
            datetime.strptime(search, "%Y-%m-%d")
            or_filters.append(["posting_date", "=", search])
        except ValueError:
            pass

    return filters, or_filters

def build_payment_detail(doc):
    allocations = [
        {
            "reference_doctype": ref.reference_doctype,
            "reference_name": ref.reference_name,
            "total_amount": ref.total_amount,
            "outstanding_amount": ref.outstanding_amount,
            "allocated_amount": ref.allocated_amount,
            "account": ref.account,
        }
        for ref in doc.get("references")
    ]

    taxes = [
        {
            "account_head": t.account_head,
            "tax_amount": t.tax_amount,
            "description": t.description,
            "rate": t.rate,
        }
        for t in doc.get("taxes")
    ]

    deductions = [
        {"account": d.account, "amount": d.amount, "description": d.description}
        for d in doc.get("deductions")
    ]

    attachments = frappe.db.get_all(
        "File",
        filters={
            "attached_to_doctype": "Payment Entry",
            "attached_to_name": doc.name,
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

    paid_from_account_details = frappe.db.get_value(
        "Account", doc.paid_from, ["account_name", "account_number"], as_dict=True
    )
    paid_to_account_details = frappe.db.get_value(
        "Account", doc.paid_to, ["account_name", "account_number"], as_dict=True
    )

    return {
        "header": {
            "payment_id": doc.name,
            "payment_type": doc.payment_type,
            "status": doc.status,
            "posting_date": doc.posting_date,
            "company": doc.company,
            "naming_series": doc.naming_series,
        },
        "party_info": {
            "party_type": doc.party_type,
            "party": doc.party,
            "party_name": doc.party_name,
            "contact_person": doc.contact_person,
        },
        "transaction_info": {
            "mode_of_payment": doc.mode_of_payment,
            "paid_from": doc.paid_from,
            "paid_from_account_name": (
                f"{paid_from_account_details.get('account_number', '')} - {paid_from_account_details.get('account_name', '')}"
                if paid_from_account_details["account_number"]
                else paid_from_account_details.get("account_name")
            ),
            "paid_from_currency": doc.paid_from_account_currency,
            "paid_to": doc.paid_to,
            "paid_to_account_name": (
                f"{paid_to_account_details.get('account_number', '')} - {paid_to_account_details.get('account_name', '')}"
                if paid_to_account_details["account_number"]
                else paid_to_account_details.get("account_name")
            ),
            "paid_to_currency": doc.paid_to_account_currency,
            "bank": doc.bank,
            "bank_account_no": doc.bank_account_no,
            "party_bank_account": doc.party_bank_account,
            "reference_no": doc.reference_no,
            "reference_date": doc.reference_date,
            "clearance_date": doc.clearance_date,
            "cost_center": doc.cost_center,
            "project": doc.project,
        },
        "amounts": {
            "paid_amount": doc.paid_amount,
            "received_amount": doc.received_amount,
            "base_paid_amount": doc.base_paid_amount,
            "base_received_amount": doc.base_received_amount,
            "total_allocated_amount": doc.total_allocated_amount,
            "unallocated_amount": doc.unallocated_amount,
            "difference_amount": doc.difference_amount,
            "source_exchange_rate": doc.source_exchange_rate,
            "target_exchange_rate": doc.target_exchange_rate,
            "amount_in_words": doc.in_words,
        },
        "allocations": allocations,
        "taxes": taxes,
        "deductions": deductions,
        "remarks": doc.remarks,
        "contact_email": doc.contact_email,
        "attachments": attachments,
    }
