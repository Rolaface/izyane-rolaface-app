import frappe
from frappe.model.naming import NamingSeries


def get_sales_invoice_naming_series():
    meta = frappe.get_meta("Sales Invoice")
    field = meta.get_field("naming_series")

    if not field or not field.options:
        frappe.throw("Please Configure Naming Series for Sales Invoice.")

    return [
        series.strip()
        for series in field.options.splitlines()
        if series.strip()
    ]


def get_company_sequence_settings(company):
    default_settings = {
        "use_separate_sequence_for_credit_notes": False,
        "use_separate_sequence_for_sales_debit_notes": False,
    }

    if not company or not frappe.db.exists("Company", company):
        return default_settings

    company_doc = frappe.get_cached_doc("Company", company)

    if not company_doc.custom_extended_details:
        return default_settings

    details = company_doc.custom_extended_details[0]

    return {
        "use_separate_sequence_for_credit_notes": bool(
            details.use_separate_sequence_for_credit_notes
        ),
        "use_separate_sequence_for_sales_debit_notes": bool(
            details.use_separate_sequence_for_sales_debit_notes
        ),
    }


def get_return_sales_invoice(doc):
    if not (doc.is_return or doc.is_debit_note):
        return None

    if not doc.return_against:
        return None

    if not frappe.db.exists("Sales Invoice", doc.return_against):
        frappe.throw(
            f"Sales Invoice {doc.return_against} does not exist."
        )

    return frappe.get_doc(
        "Sales Invoice",
        doc.return_against,
    )


def inherit_return_values(doc):
    sales_invoice = get_return_sales_invoice(doc)

    if not sales_invoice:
        return

    if sales_invoice.currency:
        doc.currency = sales_invoice.currency

    payment_mode = None

    if sales_invoice.custom_details:
        payment_mode = sales_invoice.custom_details[0].get("payment_mode")

    if payment_mode:
        if not doc.custom_details:
            doc.append(
                "custom_details",
                {
                    "payment_mode": payment_mode,
                },
            )
        else:
            doc.custom_details[0].payment_mode = payment_mode


def get_series_prefix(naming_series, doc):
    return NamingSeries(naming_series).get_prefix()


def synchronize_shared_sequence(doc, series_list):
    settings = get_company_sequence_settings(doc.company)

    shared_series = [series_list[0]]

    if (
        len(series_list) >= 2
        and not settings["use_separate_sequence_for_credit_notes"]
    ):
        shared_series.append(series_list[1])

    if (
        len(series_list) >= 3
        and not settings["use_separate_sequence_for_sales_debit_notes"]
    ):
        shared_series.append(series_list[2])

    prefixes = sorted(
        {
            get_series_prefix(series, doc)
            for series in shared_series
        }
    )

    if not prefixes:
        return

    for prefix in prefixes:
        frappe.db.sql(
            """
            INSERT IGNORE INTO `tabSeries` (`name`, `current`)
            VALUES (%s, 0)
            """,
            (prefix,),
        )

    current_values = {}

    for prefix in prefixes:
        row = frappe.db.sql(
            """
            SELECT current
            FROM `tabSeries`
            WHERE name = %s
            FOR UPDATE
            """,
            (prefix,),
        )

        current_values[prefix] = int(row[0][0]) if row else 0

    shared_current = max(current_values.values()) if current_values else 0

    for prefix in prefixes:
        if current_values[prefix] != shared_current:
            frappe.db.sql(
                """
                UPDATE `tabSeries`
                SET current = %s
                WHERE name = %s
                """,
                (
                    shared_current,
                    prefix,
                ),
            )


def before_naming(doc, method=None):
    print("CODE VERSION: 2026-09-07-001")
    print("SERIES OPTIONS:", repr(frappe.get_meta("Sales Invoice").get_field("naming_series").options))
    print("SERIES LIST:", get_sales_invoice_naming_series())
    print("IS RETURN:", doc.is_return)
    print("IS DEBIT NOTE:", doc.is_debit_note)
    print("SITE:", frappe.local.site)
    print("SERIES OPTIONS:", repr(
        frappe.get_meta("Sales Invoice").get_field("naming_series").options
    ))
    print("SERIES LIST:", get_sales_invoice_naming_series())
    if doc.doctype != "Sales Invoice":
        return

    series_list = get_sales_invoice_naming_series()
    print("🚀 ~ before_naming ~ series_list:", series_list)

    if doc.is_debit_note:
        if len(series_list) < 3:
            frappe.throw(
                "Please Configure Naming Series for Sales Debit Note."
            )

        doc.naming_series = series_list[2]

    elif doc.is_return:
        if len(series_list) < 2:
            frappe.throw(
                "Please Configure Naming Series for Credit Notes."
            )

        doc.naming_series = series_list[1]

    elif not doc.naming_series:
        doc.naming_series = series_list[0]

    settings = get_company_sequence_settings(doc.company)

    use_shared_sequence = False

    if doc.is_debit_note:
        use_shared_sequence = not settings[
            "use_separate_sequence_for_sales_debit_notes"
        ]

    elif doc.is_return:
        use_shared_sequence = not settings[
            "use_separate_sequence_for_credit_notes"
        ]

    else:
        use_shared_sequence = (
            not settings["use_separate_sequence_for_credit_notes"]
            or not settings["use_separate_sequence_for_sales_debit_notes"]
        )

    if use_shared_sequence:
        synchronize_shared_sequence(
            doc,
            series_list,
        )


def before_insert(doc, method=None):
    if doc.doctype != "Sales Invoice":
        return

    if doc.is_return or doc.is_debit_note:
        inherit_return_values(doc)

    if not doc.company:
        frappe.throw("Company is mandatory for Sales Invoice.")


def after_insert(doc, method=None):
    if doc.doctype != "Sales Invoice":
        return

    if "zra_smart_invoice" in frappe.get_installed_apps():
        doc.db_set(
            "disable_rounded_total",
            1,
            update_modified=False,
        )