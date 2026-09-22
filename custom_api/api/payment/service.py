import frappe
from frappe.desk.search import search_widget

from custom_api.api.payment.utils import (
    PaymentEntryError,
    build_deduction,
    build_ledger_account_filters,
    build_payment_detail,
    build_payment_entry_response,
    build_payment_list_query,
    build_references,
    build_taxes,
    get_required_field_labels,
    mark_reference_pdc_used,
    resolve_exchange_rates,
    resolve_party_name,
    validate_required,
)

def get_ledger_account_service(payment_type, filter_param, txt, party_type):
    company = frappe.defaults.get_user_default("Company")
    filters = build_ledger_account_filters(payment_type, filter_param, party_type, company)

    return search_widget(
        "Account",
        txt.strip(),
        None,
        searchfield=None,
        page_length=10,
        filters=filters,
        filter_fields='["account_currency", "account_name"]',
        reference_doctype="Payment Entry",
        ignore_user_permissions=0,
        as_dict=True,
    )

def validate_and_resolve_payment_entry(data):

    if not data:
        raise PaymentEntryError("Request body is required.", 400)

    payment_type = data.get("payment_type")
    field_labels = get_required_field_labels(payment_type)
    missing = validate_required(data, field_labels)
    if missing:
        raise PaymentEntryError(f"{field_labels[missing]} is required.", 400)

    company = frappe.defaults.get_user_default("Company")
    company_currency = frappe.db.get_value("Company", company, "default_currency")

    party_type = data.get("party_type", None)
    party_id = data.get("party_id")
    payment_mode = data.get("mode_of_payment")
    payment_date = data.get("payment_date")
    reference_no = data.get("reference_no", "")
    reference_date = data.get("reference_date") or payment_date
    project = data.get("project")
    cost_center = data.get("cost_center")
    exchange_rate = float(data.get("exchange_rate") or 1)

    paid_from = data.get("paid_from")
    paid_from_bank_account = data.get("paid_from_bank_account", "")
    paid_from_currency = data.get("paid_from_account_currency", company_currency)
    paid_amount = float(data.get("paid_from_amount") or 0)

    paid_to = data.get("paid_to")
    paid_to_bank_account = data.get("paid_to_bank_account", "")
    paid_to_currency = data.get("paid_to_account_currency", company_currency)
    received_amount = float(data.get("paid_to_amount") or paid_amount)

    references = data.get("references", [])
    taxes = data.get("taxes", [])
    deductions = data.get("deductions", [])

    valid_payment_types = ["Pay", "Receive", "Internal Transfer"]
    if payment_type not in valid_payment_types:
        raise PaymentEntryError(f"'paymentType' must be one of: {', '.join(valid_payment_types)}.", 400)

    party_name = None
    if payment_type != "Internal Transfer":
        valid_party_types = ["Customer", "Supplier", "Employee", "Shareholder"]
        if party_type not in valid_party_types:
            raise PaymentEntryError(f"'partyType' must be one of: {', '.join(valid_party_types)}.", 400)

        party_name = data.get("party_id") or resolve_party_name(party_type, party_id)
        if not party_name:
            raise PaymentEntryError(f"{party_type} with ID '{party_id}' not found.", 404)

    if party_type in ["Customer", "Supplier", "Employee"]:  # Later on we need to handle Shareholder as well
        if not references or len(references) == 0:
            raise PaymentEntryError(
                "At least one Purchase Invoice, Purchase Order, or Sales Invoice must be provided to create a payment entry.",
                400,
            )

    if not (
        paid_from_currency == paid_to_currency
        or paid_from_currency == company_currency
        or paid_to_currency == company_currency
    ):
        raise PaymentEntryError(
            "Invalid currency combination: 'paid from account currency' "
            "and 'paid to account currency' must either be the same "
            f"or one of them must be the company default currency ({company_currency}).",
            400,
        )

    source_exchange_rate, target_exchange_rate = resolve_exchange_rates(
        paid_from_currency, paid_to_currency, company_currency, payment_date, exchange_rate
    )

    total_deduction = 0
    if deductions:          # @TODO: Need to handle deductions for PI, PO, etc. Currently only tested for SI in base currency
        total_deduction = sum(float(d.get("amount") or 0) for d in deductions)

    return {
        "company": company,
        "payment_type": payment_type,
        "payment_date": payment_date,
        "payment_mode": payment_mode,
        "party_type": party_type,
        "party_name": party_name,
        "paid_from": paid_from,
        "paid_to": paid_to,
        "paid_from_bank_account": paid_from_bank_account,
        "paid_to_bank_account": paid_to_bank_account,
        "paid_from_currency": paid_from_currency,
        "paid_to_currency": paid_to_currency,
        "paid_amount": paid_amount - total_deduction,
        "received_amount": received_amount,
        "source_exchange_rate": source_exchange_rate,
        "target_exchange_rate": target_exchange_rate,
        "reference_no": reference_no,
        "reference_date": reference_date,
        "project": project,
        "cost_center": cost_center,
        "references": references,
        "taxes": taxes,
        "deductions": deductions,
    }

def apply_payment_entry_fields(pe, resolved):

    pe.payment_type = resolved["payment_type"]
    pe.posting_date = resolved["payment_date"]
    pe.company = resolved["company"]
    pe.mode_of_payment = resolved["payment_mode"]
    pe.party_type = resolved["party_type"]
    pe.party = resolved["party_name"]
    pe.paid_from = resolved["paid_from"]
    pe.paid_to = resolved["paid_to"]
    pe.paid_from_account_currency = resolved["paid_from_currency"]
    pe.paid_to_account_currency = resolved["paid_to_currency"]
    pe.paid_amount = resolved["paid_amount"]
    pe.received_amount = resolved["received_amount"]
    pe.source_exchange_rate = resolved["source_exchange_rate"]
    pe.target_exchange_rate = resolved["target_exchange_rate"]
    pe.reference_no = resolved["reference_no"]
    pe.reference_date = resolved["reference_date"]

    if resolved["paid_from_bank_account"]:
        pe.bank_account = resolved["paid_from_bank_account"]

    if resolved["paid_to_bank_account"]:
        pe.party_bank_account = resolved["paid_to_bank_account"]

    if resolved["project"]:
        pe.project = resolved["project"]

    if resolved["cost_center"]:
        pe.cost_center = resolved["cost_center"]

    if resolved["references"]:
        build_references(resolved["references"], pe)

    if resolved["taxes"]:
        build_taxes(resolved["taxes"], pe)

    if resolved["deductions"]:
        build_deduction(resolved["deductions"], pe)


def create_payment_entry_service(data):
    resolved = validate_and_resolve_payment_entry(data)

    pe = frappe.new_doc("Payment Entry")
    apply_payment_entry_fields(pe, resolved)
    pe.insert(ignore_permissions=True)

    mark_reference_pdc_used(resolved["reference_no"])

    return build_payment_entry_response(pe)

def update_payment_entry_service(payment_id, data):
    if not frappe.db.exists("Payment Entry", payment_id):
        raise PaymentEntryError(f"Payment Entry '{payment_id}' not found.", 404)

    pe = frappe.get_doc("Payment Entry", payment_id)
    if pe.docstatus != 0:
        raise PaymentEntryError("Only Draft Payment Entries can be updated.", 400)

    resolved = validate_and_resolve_payment_entry(data)
    apply_payment_entry_fields(pe, resolved)
    pe.save(ignore_permissions=True)

    mark_reference_pdc_used(resolved["reference_no"])

    return build_payment_entry_response(pe)

def get_all_payments_service(args):
    try:
        page = int(args.get("page", 1))
        if page < 1:
            raise ValueError
    except ValueError:
        raise PaymentEntryError("'page' must be a positive integer.", 400)

    try:
        page_size = int(args.get("pageSize", 10))
        if page_size < 1:
            raise ValueError
    except ValueError:
        raise PaymentEntryError("'page_size' must be a positive integer.", 400)

    start_index = (page - 1) * page_size

    filters, or_filters = build_payment_list_query(args)

    order_by = args.get("order_by", "creation desc")

    payments = frappe.get_all(
        "Payment Entry",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name as paymentId",
            "payment_type as paymentType",
            "party_type as partyType",
            "party",
            "party_name as partyName",
            "mode_of_payment as paymentMode",
            "posting_date as paymentDate",
            "paid_amount as amount",
            "paid_from_account_currency as paidCurrency",
            "paid_to_account_currency as receivedCurrency",
            "reference_no as referenceNumber",
            "status",
        ],
        order_by=order_by,
        start=start_index,
        page_length=page_size,
    )

    total_payments = len(
        frappe.get_all("Payment Entry", filters=filters, or_filters=or_filters, pluck="name")
    )

    if total_payments == 0:
        return {"payments": [], "pagination": None}

    total_pages = (total_payments + page_size - 1) // page_size

    return {
        "payments": payments,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total_payments,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        },
    }

def get_payment_by_id_service(payment_id):
    if not frappe.db.exists("Payment Entry", payment_id):
        raise PaymentEntryError(f"Payment Entry '{payment_id}' not found.", 404)

    doc = frappe.get_doc("Payment Entry", payment_id)
    return build_payment_detail(doc)
