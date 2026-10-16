import frappe
import json
from typing import Dict, Any
from frappe.utils import flt, cint, add_days

def get_naming_series_for_quotation(document_type: str) -> str:
    meta = frappe.get_meta("Quotation")
    naming_series_field = meta.get_field("naming_series")
    
    if not naming_series_field or not naming_series_field.options:
        frappe.throw("Naming Series options for Quotation are not configured in the system.")

    series_list = [s.strip() for s in naming_series_field.options.split('\n') if s.strip()]
    
    if not series_list:
        frappe.throw("Naming Series options for Quotation are empty. Please configure them in Document Naming Settings.")

    if document_type == "Proforma Invoice":
        if len(series_list) < 2:
            frappe.throw("Proforma Invoice naming series not found. Please add a second line to the Quotation Naming Series options.")
        return series_list[1]
    
    return series_list[0]

def validate_quotation_payload(data: Dict[str, Any], is_update=False):
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
    valid_till = data.get("validTill")
    document_type = data.get("documentType") or data.get("document_type")
    if posting_date and valid_till:
        if valid_till < posting_date:
            field_name = "Due date" if document_type == "Proforma Invoice" else "Valid till date"
            raise frappe.ValidationError(f"{field_name} cannot be before Posting Date.")

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


def sync_quotation_terms(quotation, terms_payload):
    terms_data = terms_payload.get("Selling") or terms_payload.get("selling")
    if not terms_data:
        return

    is_quotation_dirty = False

    pt_name = f"{quotation.name} PT"
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

            quotation.payment_terms_template = pt_doc.name
            quotation.set("payment_schedule", [])

            base_date = quotation.transaction_date or frappe.utils.today()

            for phase in phases:
                credit_days = cint(phase.get("credit_days", 0))
                calculated_due_date = add_days(base_date, credit_days)

                quotation.append(
                    "payment_schedule",
                    {
                        "payment_term": phase.get("name"),
                        "description": phase.get("condition", ""),
                        "invoice_portion": flt(phase.get("percentage")),
                        "due_date": calculated_due_date,
                    },
                )
            is_quotation_dirty = True
        else:
            raise frappe.ValidationError(
                f"Payment phases must sum to exactly 100%. Current sum: {round(total_pct, 2)}%"
            )

    tc_name = f"{quotation.name} Terms"
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

    quotation.tc_name = tc_name
    quotation.terms = tc_content
    is_quotation_dirty = True

    if is_quotation_dirty:
        quotation.save(ignore_permissions=True)


def sync_taxes(quotation, data):
    quotation.set("taxes", [])

    default_cc = quotation.get("cost_center") or frappe.get_cached_value(
        "Company", quotation.company, "cost_center"
    )
    existing_heads = set()
    is_dirty = False

    template_name = data.get("salesTaxTemplate") or quotation.taxes_and_charges
    if template_name and frappe.db.exists(
        "Sales Taxes and Charges Template", template_name
    ):
        template = frappe.get_cached_doc(
            "Sales Taxes and Charges Template", template_name
        )
        for t_row in template.taxes:
            quotation.append(
                "taxes",
                {
                    "charge_type": t_row.charge_type,
                    "account_head": t_row.account_head,
                    "description": t_row.description,
                    "cost_center": t_row.cost_center or default_cc,
                    "rate": t_row.rate,
                    "tax_amount": t_row.tax_amount,
                },
            )
            existing_heads.add(t_row.account_head)
            is_dirty = True

    for item in quotation.get("items", []):
        item_tax_template = item.get("item_tax_template") or getattr(
            item, "item_tax_template", None
        )
        if item_tax_template:
            item_tax_doc = frappe.get_cached_doc("Item Tax Template", item_tax_template)
            for it in item_tax_doc.taxes:
                if it.tax_type not in existing_heads:
                    quotation.append(
                        "taxes",
                        {
                            "charge_type": "On Net Total",
                            "account_head": it.tax_type,
                            "description": it.tax_type,
                            "cost_center": default_cc,
                            "rate": 0,
                            "tax_amount": 0,
                        },
                    )
                    existing_heads.add(it.tax_type)
                    is_dirty = True

    tax_overrides = data.get("taxes", [])
    if tax_overrides:
        override_map = {
            t.get("accountHead"): t for t in tax_overrides if t.get("accountHead")
        }

        for tax_row in quotation.get("taxes", []):
            override = override_map.get(tax_row.account_head)
            if not override:
                continue

            charge_type = override.get("chargeType") or override.get("charge_type")

            amount = override.get("amount")
            rate = override.get("rate")
            description = override.get("description")

            if charge_type == "Actual" and rate is not None:
                frappe.throw(f"{tax_row.account_head}: 'Actual' cannot have rate")

            if charge_type and charge_type != "Actual" and amount is not None:
                frappe.throw(f"{tax_row.account_head}: Only 'Actual' can have amount")

            if charge_type:
                tax_row.charge_type = charge_type

            if description is not None:
                tax_row.description = description
                is_dirty = True

            if amount is not None:
                tax_row.tax_amount = flt(amount)
                tax_row.rate = 0
                if not charge_type:
                    tax_row.charge_type = "Actual"
                is_dirty = True

            elif rate is not None:
                tax_row.rate = flt(rate)
                tax_row.tax_amount = 0
                if not charge_type and tax_row.charge_type == "Actual":
                    tax_row.charge_type = "On Net Total"
                is_dirty = True

    return is_dirty


def build_quotation_filters(args):
    frappe_filters = {}

    if not args:
        return frappe_filters

    if args.get("party_name"):
        frappe_filters["party_name"] = args["party_name"]

    if args.get("status"):
        frappe_filters["status"] = ["in", args["status"]]

    if args.get("from_date") and args.get("to_date"):
        frappe_filters["transaction_date"] = [
            "between",
            [args["from_date"], args["to_date"]],
        ]

    if args.get("company"):
        frappe_filters["company"] = args["company"]

    if args.get("status"):
        frappe_filters["status"] = ["in", args["status"]]

    doc_type = args.get("documentType") or args.get("document_type")
    if doc_type:
        matching_parents = frappe.get_all(
            "Custom Quotation Extended Details",
            filters={"document_type": doc_type},
            pluck="parent"
        )
        if matching_parents:
            frappe_filters["name"] = ["in", matching_parents]
        else:
            frappe_filters["name"] = "---not-found---"

    return frappe_filters

def _build_quotation_box_detail(item: dict) -> dict:
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
        fields=["hsn_code", "packing_unit", "packing_size"],
    )

def ensure_lost_reason(lost_reason):
    if not lost_reason:
        return
    
    if not frappe.db.exists("Quotation Lost Reason", lost_reason):
        frappe.get_doc({
            "doctype": "Quotation Lost Reason",
            "order_lost_reason": lost_reason
        }).insert(ignore_permissions=True)