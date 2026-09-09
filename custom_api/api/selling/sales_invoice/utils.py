import frappe
from typing import Dict, Any
import json
from frappe.utils import flt, cint, add_days
from erpnext.setup.utils import get_exchange_rate

def get_lpo_tax_template(company=None):
    company = company or frappe.defaults.get_user_default("Company")

    filters = {"name": ["like", "%C2%"]}
    if company:
        filters["company"] = company

    template_name = frappe.db.get_value(
        "Item Tax Template",
        filters,
        "name",
        order_by="creation asc",
    )

    if not template_name:
        frappe.throw(
            "No Item Tax Template found matching 'C2' (LPO zero-rating template). "
            "Please ensure it exists for the current company."
        )

    return template_name

def get_zero_rated_tax_template(company=None):
    company = company or frappe.defaults.get_user_default("Company")

    filters = {"name": ["like", "%TOT%"]}
    if company:
        filters["company"] = company

    template_name = frappe.db.get_value(
        "Item Tax Template",
        filters,
        "name",
        order_by="creation asc",
    )

    if not template_name:
        frappe.throw(
            "No Item Tax Template found matching 'C2' (LPO zero-rating template). "
            "Please ensure it exists for the current company."
        )

    return template_name

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
                # )


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

# def sync_taxes(invoice, data):
#     invoice.set("taxes", [])

#     default_cc = invoice.cost_center or frappe.get_cached_value("Company", invoice.company, "cost_center")
#     existing_heads = set()
#     is_dirty = False

#     template_name = data.get("salesTaxTemplate") or invoice.taxes_and_charges
#     if template_name and frappe.db.exists("Sales Taxes and Charges Template", template_name):
#         template = frappe.get_cached_doc("Sales Taxes and Charges Template", template_name)
#         for t_row in template.taxes:
#             invoice.append("taxes", {
#                 "charge_type": t_row.charge_type,
#                 "account_head": t_row.account_head,
#                 "description": t_row.description,
#                 "cost_center": t_row.cost_center or default_cc,
#                 "rate": t_row.rate,
#                 "tax_amount": t_row.tax_amount,
#             })
#             existing_heads.add(t_row.account_head)
#             is_dirty = True

#     for item in invoice.get("items", []):
#         if item.item_tax_template:
#             item_tax_doc = frappe.get_cached_doc("Item Tax Template", item.item_tax_template)
#             for it in item_tax_doc.taxes:
#                 if it.tax_type not in existing_heads:
#                     invoice.append("taxes", {
#                         "charge_type": "On Net Total", 
#                         "account_head": it.tax_type,
#                         "description": it.tax_type, 
#                         "cost_center": default_cc,
#                         "rate": 0,
#                         "tax_amount": 0,
#                     })
#                     existing_heads.add(it.tax_type)
#                     is_dirty = True

#     tax_overrides = data.get("taxes", [])
#     if tax_overrides:
#         override_map = {
#             t.get("accountHead"): t for t in tax_overrides if t.get("accountHead")
#         }

#         for tax_row in invoice.get("taxes", []):
#             override = override_map.get(tax_row.account_head)
#             if not override:
#                 continue

#             charge_type = override.get("chargeType") or override.get("charge_type")

#             amount = override.get("amount")
#             rate = override.get("rate")
#             description = override.get("description")

#             if charge_type == "Actual" and rate is not None:
#                 frappe.throw(f"{tax_row.account_head}: 'Actual' cannot have rate")

#             if charge_type and charge_type != "Actual" and amount is not None:
#                 frappe.throw(f"{tax_row.account_head}: Only 'Actual' can have amount")

#             if charge_type:
#                 tax_row.charge_type = charge_type
            
#             if description is not None:
#                 tax_row.description = description
#                 is_dirty = True

#             if amount is not None:
#                 tax_row.tax_amount = flt(amount)
#                 tax_row.rate = 0
#                 if not charge_type:
#                     tax_row.charge_type = "Actual"
#                 is_dirty = True

#             elif rate is not None:
#                 tax_row.rate = flt(rate)
#                 tax_row.tax_amount = 0
#                 if not charge_type and tax_row.charge_type == "Actual":
#                     tax_row.charge_type = "On Net Total"
#                 is_dirty = True

#     return is_dirty

def update_item_tax_doc(item_tax_doc):
    installed_apps = frappe.get_installed_apps()
    if "zra_smart_invoice" in installed_apps:
        tax = item_tax_doc.taxes
        title = item_tax_doc.title
        categories_part = title.split("|")[-1].strip()
        categories = [c.strip() for c in categories_part.split(",") if c.strip()]
        if "Insurance Premium Levy" in categories:
            index = categories.index("Insurance Premium Levy")
            if index < len(tax):
                row_to_keep = tax[index]
                item_tax_doc.set("taxes", [row_to_keep])
                return item_tax_doc

    return item_tax_doc

def create_tax_payload(tax_head, default_cc, item_tax, previous_row):
    installed_apps = frappe.get_installed_apps()
    if "zra_smart_invoice" in installed_apps:
        if previous_row is None:
            charge_type = "On Net Total"
            row_id = None
        else:
            charge_type = "On Previous Row Total"
            row_id = previous_row.idx

        return {
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": charge_type,
                    "account_head": tax_head,
                    "description": tax_head,
                    "cost_center": default_cc,
                    "rate": item_tax.tax_rate,
                    "tax_amount": 0,
                    "row_id": row_id,
                }
    else:
        return {
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": "On Net Total",
                    "account_head": tax_head,
                    "description": tax_head,
                    "cost_center": default_cc,
                    "rate": 0,
                    "tax_amount": 0,
                    "row_id": None,
                }

def sync_taxes(invoice, data):
    # Clear any taxes that may have been populated automatically
    invoice.set("taxes", [])

    default_cc = (
        invoice.cost_center
        or frappe.get_cached_value(
            "Company",
            invoice.company,
            "cost_center",
        )
    )

    existing_heads = set()
    is_dirty = False

    # =========================================================
    # 1. ADD TAXES FROM SALES TAXES AND CHARGES TEMPLATE
    # =========================================================
    template_name = (
        data.get("salesTaxTemplate")
        or invoice.taxes_and_charges
    )

    if (
        template_name
        and frappe.db.exists(
            "Sales Taxes and Charges Template",
            template_name,
        )
    ):
        template = frappe.get_cached_doc(
            "Sales Taxes and Charges Template",
            template_name,
        )

        for t_row in template.taxes:

            invoice.append(
                "taxes",
                {
                    "doctype": "Sales Taxes and Charges",
                    "charge_type": t_row.charge_type,
                    "account_head": t_row.account_head,
                    "description": t_row.description,
                    "cost_center": t_row.cost_center or default_cc,
                    "rate": flt(t_row.rate),
                    "tax_amount": flt(t_row.tax_amount),

                    # IMPORTANT:
                    # Required for "On Previous Row Amount/Total"
                    "row_id": t_row.row_id,
                },
            )

            existing_heads.add(t_row.account_head)
            is_dirty = True

    # =========================================================
    # 2. ADD MISSING TAX HEADS FROM ITEM TAX TEMPLATES
    # =========================================================
    for item in invoice.get("items", []):

        if not item.item_tax_template:
            continue

        item_tax_doc = frappe.get_cached_doc(
            "Item Tax Template",
            item.item_tax_template,
        )
        item_tax_doc = update_item_tax_doc(item_tax_doc)
        previous_row = None
        for item_tax in item_tax_doc.taxes:

            tax_head = item_tax.tax_type

            # Already added from Sales Tax Template
            if tax_head in existing_heads:
                continue

            taxes = create_tax_payload(tax_head, default_cc, item_tax, previous_row)
            new_row = invoice.append("taxes",taxes)
            # invoice.append(
            #     "taxes",
            #     {
            #         "doctype": "Sales Taxes and Charges",
            #         "charge_type": "On Net Total",
            #         "account_head": tax_head,
            #         "description": tax_head,
            #         "cost_center": default_cc,
            #         "rate": 0,
            #         "tax_amount": 0,
            #         "row_id": None,
            #     },
            # )

            previous_row = new_row
            existing_heads.add(tax_head)
            is_dirty = True

    # =========================================================
    # 3. APPLY TAX OVERRIDES FROM API PAYLOAD
    # =========================================================
    tax_overrides = data.get("taxes") or []

    if tax_overrides:

        override_map = {
            tax.get("accountHead"): tax
            for tax in tax_overrides
            if tax.get("accountHead")
        }

        for tax_row in invoice.get("taxes", []):

            override = override_map.get(tax_row.account_head)

            if not override:
                continue

            charge_type = (
                override.get("chargeType")
                or override.get("charge_type")
            )

            amount = override.get("amount")
            rate = override.get("rate")
            description = override.get("description")

            # -------------------------------------------------
            # VALIDATION
            # -------------------------------------------------
            if charge_type == "Actual" and rate is not None:
                frappe.throw(
                    f"{tax_row.account_head}: "
                    "'Actual' cannot have a rate"
                )

            if (
                charge_type
                and charge_type != "Actual"
                and amount is not None
            ):
                frappe.throw(
                    f"{tax_row.account_head}: "
                    "Only 'Actual' can have an amount"
                )

            # -------------------------------------------------
            # CHARGE TYPE
            # -------------------------------------------------
            if charge_type:
                tax_row.charge_type = charge_type
                is_dirty = True

            # -------------------------------------------------
            # DESCRIPTION
            # -------------------------------------------------
            if description is not None:
                tax_row.description = description
                is_dirty = True

            # -------------------------------------------------
            # ACTUAL AMOUNT
            # -------------------------------------------------
            if amount is not None:

                tax_row.tax_amount = flt(amount)
                tax_row.rate = 0

                if not charge_type:
                    tax_row.charge_type = "Actual"

                is_dirty = True

            # -------------------------------------------------
            # RATE
            # -------------------------------------------------
            elif rate is not None:

                tax_row.rate = flt(rate)
                tax_row.tax_amount = 0

                if (
                    not charge_type
                    and tax_row.charge_type == "Actual"
                ):
                    tax_row.charge_type = "On Net Total"

                is_dirty = True

    # =========================================================
    # 4. VALIDATE ROW IDs
    # =========================================================
    for idx, tax_row in enumerate(invoice.get("taxes", []), start=1):

        # These charge types require a Row ID
        if tax_row.charge_type in (
            "On Previous Row Amount",
            "On Previous Row Total",
        ):

            if not tax_row.row_id:
                frappe.throw(
                    f"Please specify a valid Row ID "
                    f"for row {idx} in table Sales Taxes and Charges"
                )

            # Ensure Row ID points to an existing previous row
            if int(tax_row.row_id) >= idx:
                frappe.throw(
                    f"Invalid Row ID {tax_row.row_id} "
                    f"for tax row {idx}. "
                    f"Row ID must refer to a previous row."
                )

    # =========================================================
    # DEBUG
    # =========================================================
    print("\n========== TAX ROWS BEFORE INSERT ==========")

    for i, tax in enumerate(invoice.get("taxes", []), start=1):
        print(
            {
                "row": i,
                "name": tax.get("name"),
                "idx": tax.get("idx"),
                "row_id": tax.get("row_id"),
                "doctype": tax.get("doctype"),
                "parent": tax.get("parent"),
                "parenttype": tax.get("parenttype"),
                "parentfield": tax.get("parentfield"),
                "account_head": tax.get("account_head"),
                "charge_type": tax.get("charge_type"),
                "rate": tax.get("rate"),
                "tax_amount": tax.get("tax_amount"),
            }
        )

    print("===========================================\n")

    return is_dirty


def build_sales_invoice_filters(args):

    frappe_filters = {
        "is_return": 0,
        "is_debit_note": 0,
    }

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

def ensure_batch(item_code, batch_no, mfg_date=None, exp_date=None, barcode=None):
    if not batch_no or not item_code:
        return
    if not frappe.db.exists("Batch", batch_no):
        item_payload = {
                "doctype": "Batch",
                "batch_id": batch_no,
                "item": item_code,
                "manufacturing_date": mfg_date,
                "expiry_date": exp_date,
            }
        if barcode:
            item_payload["custom_barcode"] = barcode
        frappe.get_doc(
            item_payload
        ).insert(ignore_permissions=True)


def validate_receivable_account_for_currency(currency: str, account_type="Receivable", root_type = "Asset") -> str:
    if not currency:
        frappe.throw("Currency is required.", frappe.ValidationError)

    company = frappe.defaults.get_user_default("Company")
    if not company:
        frappe.throw("Default company not set.", frappe.ValidationError)

    account = get_receivable_account_by_currency(currency, company, account_type, root_type)

    if not account:
        frappe.throw(
            f"No {account_type} account configured for currency '{currency}' in company '{company}'.",
            frappe.ValidationError,
        )

    return account


def get_receivable_account_by_currency(currency: str, company: str, account_type, root_type) -> str | None:
    return frappe.db.get_value(
        "Account",
        {
            "account_type": account_type,
            "company": company,
            "account_currency": currency,
            "root_type": root_type,
            "is_group": 0,
            "disabled": 0,
        },
        "name",
        order_by="creation asc",
    )

def _build_additional_detail(data: dict) -> dict | None:
    payment_mode = data.get("paymentMode") or data.get("payment_mode")
    invoice_type = data.get("invoiceType", "")
    principal_details = data.get("principal") or data.get("principalDetails") or data.get("principal_details")
    
    if not payment_mode and not invoice_type and not principal_details:
        return None

    details = {
        "payment_mode": payment_mode,
        "invoice_type": invoice_type
    }

    if invoice_type == "RVAT" and principal_details:
        details["zra_principal_detail"] = (
            json.dumps(principal_details) 
            if isinstance(principal_details, dict) 
            else principal_details
        )

    return details


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

def get_already_credited_qty(invoice_id):
    rows = frappe.db.sql(
        """
        SELECT child.item_code, COALESCE(child.batch_no, '') as batch_no, SUM(ABS(child.qty)) as credited_qty
        FROM `tabSales Invoice Item` child
        INNER JOIN `tabSales Invoice` parent ON parent.name = child.parent
        WHERE parent.return_against = %s
          AND parent.docstatus = 1
          AND (parent.is_return = 1 OR parent.is_debit_note = 1)
        GROUP BY child.item_code, child.batch_no
        """,
        (invoice_id,),
        as_dict=True,
    )

    credited_map = {}
    for row in rows:
        key = (row.item_code, row.batch_no or "")
        credited_map[key] = flt(row.credited_qty)

    return credited_map