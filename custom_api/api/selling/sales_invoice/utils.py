import frappe
from typing import Dict, Any
import json
from frappe.utils import flt, cint, add_days
from erpnext.setup.utils import get_exchange_rate


def validate_sales_invoice_payload(data: Dict[str, Any], is_update=False):
    if not is_update and not data.get("customerId"):
        raise frappe.ValidationError("customerId is required.")

    if not is_update and not frappe.db.exists("Customer", data.get("customerId")):
        raise frappe.ValidationError(
            f"Customer {data.get('customerId')} does not exist."
        )

    items = data.get("items")
    if items is not None:
        if not isinstance(items, list) or len(items) == 0:
            raise frappe.ValidationError(
                "At least one item is required in the 'items' array."
            )

        for idx, item in enumerate(items):
            if not item.get("itemCode"):
                raise frappe.ValidationError(f"Row {idx+1}: itemCode is required.")
            if not item.get("quantity") or float(item.get("quantity")) <= 0:
                raise frappe.ValidationError(
                    f"Row {idx+1}: quantity must be greater than 0."
                )
            if not frappe.db.exists("Item", item.get("itemCode")):
                raise frappe.ValidationError(
                    f"Row {idx+1}: Item {item.get('itemCode')} does not exist."
                )

    posting_date = data.get("postingDate")
    due_date = data.get("dueDate")
    if posting_date and due_date:
        if due_date < posting_date:
            raise frappe.ValidationError("dueDate cannot be before postingDate.")

    terms = data.get("terms")
    if terms:
        phases = terms.get("selling", {}).get("payment", {}).get("phases", [])
        if phases:
            total_percentage = sum(
                float(phase.get("percentage", 0)) for phase in phases
            )
            if total_percentage != 100:
                raise frappe.ValidationError(
                    f"Total percentage of payment phases must equal 100. Currently: {total_percentage}"
                )   
    # company_currency = frappe.defaults.get_user_default("Currency")
    # currency = data.get("currency") or company_currency

    # if currency and currency != company_currency:
    #     exchange_rate = data.get("exchangeRate")

    #     if exchange_rate:
    #         if float(exchange_rate) <= 0:
    #             raise frappe.ValidationError(
    #                 "exchangeRate must be greater than 0."
    #             )
    #     else:
    #         try:
    #             rate = get_exchange_rate(
    #                 currency,
    #                 company_currency,
    #                 posting_date,
    #             )
    #         except Exception:
    #             rate = None

    #         if not rate:
    #             raise frappe.ValidationError(
    #                 f"No exchange rate found for {currency} → {company_currency} on {posting_date}. "
    #                 f"Please maintain Currency Exchange."
                )


def sync_invoice_terms(invoice, terms_payload):
    terms_data = terms_payload.get("Selling") or terms_payload.get("selling")
    if not terms_data:
        return

    is_invoice_dirty = False

    pt_name = f"{invoice.name} PT"
    phases = terms_data.get("payment", {}).get("phases", [])

    if phases:
        if not frappe.db.exists("Payment Terms Template", pt_name):
            pt_doc = frappe.get_doc(
                {"doctype": "Payment Terms Template", "template_name": pt_name}
            )
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
                frappe.get_doc(
                    {
                        "doctype": "Payment Term",
                        "payment_term_name": term_name,
                        "description": phase.get("condition", ""),
                        "invoice_portion": pct,
                        "due_date_based_on": "Day(s) after invoice date",
                        "credit_days": credit_days,
                    }
                ).insert(ignore_permissions=True)
            else:
                pt = frappe.get_doc("Payment Term", term_name)
                pt.description = phase.get("condition", "")
                pt.invoice_portion = pct
                pt.credit_days = credit_days
                pt.save(ignore_permissions=True)

            pt_doc.append(
                "terms",
                {
                    "payment_term": term_name,
                    "invoice_portion": pct,
                    "credit_days": credit_days,
                },
            )

        if round(total_pct, 2) == 100.00:
            pt_doc.save(ignore_permissions=True)

            invoice.payment_terms_template = pt_doc.name
            invoice.set("payment_schedule", [])

            base_date = invoice.posting_date or frappe.utils.today()

            for phase in phases:
                credit_days = cint(phase.get("credit_days", 0))
                calculated_due_date = add_days(base_date, credit_days)

                invoice.append(
                    "payment_schedule",
                    {
                        "payment_term": phase.get("name"),
                        "description": phase.get("condition", ""),
                        "invoice_portion": flt(phase.get("percentage")),
                        "due_date": calculated_due_date,
                    },
                )
            is_invoice_dirty = True
        else:
            raise frappe.ValidationError(
                f"Payment phases must sum to exactly 100%. Current sum: {round(total_pct, 2)}%"
            )

    tc_name = f"{invoice.name} Terms"
    tc_content = json.dumps(terms_data, indent=2)

    if frappe.db.exists("Terms and Conditions", tc_name):
        tc_doc = frappe.get_doc("Terms and Conditions", tc_name)
        tc_doc.terms = tc_content
        tc_doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": "Terms and Conditions",
                "title": tc_name,
                "terms": tc_content,
                "selling": 1,
            }
        ).insert(ignore_permissions=True)

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
    override_map = {
        t.get("accountHead"): t for t in tax_overrides if t.get("accountHead")
    }

    if template_name and frappe.db.exists(
        "Sales Taxes and Charges Template", template_name
    ):
        template = frappe.get_doc("Sales Taxes and Charges Template", template_name)
        existing_heads = [t.account_head for t in invoice.get("taxes", [])]

        for t_row in template.taxes:
            if t_row.account_head not in existing_heads:
                invoice.append(
                    "taxes",
                    {
                        "charge_type": t_row.charge_type,
                        "account_head": t_row.account_head,
                        "description": t_row.description,
                        "cost_center": t_row.cost_center,
                        "rate": t_row.rate,
                        "tax_amount": t_row.tax_amount,
                    },
                )
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

def build_sales_invoice_filters(args):

    frappe_filters = {}

    if not args:
        return frappe_filters
    minOutstanding= args.get("minOutstanding")
    maxOutstanding = args.get("maxOutstanding")
    if args.get("customer"):
        frappe_filters["customer"] = args["customer"]

    if args.get("status"):
        frappe_filters["status"] = ["in", args["status"]]

    if args.get("from_date") and args.get("to_date"):
        frappe_filters["posting_date"] = ["between", [args["from_date"], args["to_date"]]]

    if args.get("company"):
        frappe_filters["company"] = args["company"]

    if minOutstanding and maxOutstanding:
        frappe_filters["outstanding_amount"] = ["between", [float(minOutstanding), float(maxOutstanding)]]
    elif minOutstanding:
        frappe_filters["outstanding_amount"] = [">=", float(minOutstanding)]
    elif maxOutstanding:
        frappe_filters["outstanding_amount"] = ["<=", float(maxOutstanding)]

    return frappe_filters                           

def ensure_batch(item_code, batch_no, mfg_date=None, exp_date=None):
    if not batch_no or not item_code:
        return
    if not frappe.db.exists("Batch", batch_no):
        frappe.get_doc(
            {
                "doctype": "Batch",
                "batch_id": batch_no,
                "item": item_code,
                "manufacturing_date": mfg_date,
                "expiry_date": exp_date,
            }
        ).insert(ignore_permissions=True)


def validate_receivable_account_for_currency(currency: str, account_type="Receivable") -> str:
    if not currency:
        frappe.throw("Currency is required.", frappe.ValidationError)

    company = frappe.defaults.get_user_default("Company")
    if not company:
        frappe.throw("Default company not set.", frappe.ValidationError)

    account = get_receivable_account_by_currency(currency, company, account_type)

    if not account:
        frappe.throw(
            f"No {account_type} account configured for currency '{currency}' in company '{company}'.",
            frappe.ValidationError,
        )

    return account


def get_receivable_account_by_currency(currency: str, company: str, account_type) -> str | None:
    return frappe.db.get_value(
        "Account",
        {
            "account_type": account_type,
            "company": company,
            "account_currency": currency,
            "is_group": 0,
            "disabled": 0,
        },
        "name",
        order_by="creation asc",
    )

def _build_additional_detail(data: dict) -> dict | None:
    payment_mode = data.get("paymentMode") or data.get("payment_mode")

    if not payment_mode:
        return None

    return {
        "payment_mode": payment_mode
    }


def _build_sales_invoice_box_detail(item: dict) -> dict:
    return {
        "item_code": item.get("itemCode"),
        "batch_no": item.get("batchNo") or item.get("batch_no"),
        "box_start": item.get("boxStart") or item.get("box_start"),
        "box_end": item.get("boxEnd") or item.get("box_end"),
    }

def get_extended_item_detail(item_code):
    return frappe.get_all(
        "Custom Item Details",
        filters={"parent": item_code},
        fields=["hsn_code","packing_unit","packing_size"]
    )

def get_payment_information(mode_of_payment, company):
    if not mode_of_payment:
        return None

    mop = frappe.get_doc("Mode of Payment", mode_of_payment)

    default_account = None
    for acc in mop.accounts:
        if acc.company == company:
            default_account = acc.default_account
            break

    if not default_account:
        return None

    bank_account = frappe.db.get_value(
        "Bank Account",
        {"account": default_account},
        [
            "account_name",
            "bank",
            "bank_account_no",
            "branch_code",
            "iban",
            "account",
        ],
        as_dict=True,
    )

    if not bank_account:
        return {
            "mode": mode_of_payment,
        }

    swift_code = frappe.db.get_value(
        "Bank",
        bank_account.bank,
        "swift_number"
    )

    currency = frappe.db.get_value(
        "Account",
        bank_account.account,
        "account_currency"
    )

    return {
        "paymentMethod": mode_of_payment,
        "type": "Bank",
        "accountHolderName": bank_account.account_name,
        "bankName": bank_account.bank,
        "accountNumber": bank_account.bank_account_no,
        "branchCode": bank_account.branch_code,
        "swiftCode": swift_code,
        "routingNumber": bank_account.iban,
        "currency": currency,
    }