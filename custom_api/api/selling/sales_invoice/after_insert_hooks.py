import frappe

def get_series_prefix(naming_series: str) -> str:
    """Extract the tabSeries key from a naming series template.
    e.g. 'RSSI/2627/.###.' -> 'RSSI/2627/'
    """
    prefix = ""
    for part in naming_series.split("."):
        if not part:
            continue
        if part.startswith("#"):
            break
        prefix += part
    return prefix

def after_insert(doc, method):
    installed_apps = frappe.get_installed_apps()
    if "zra_smart_invoice" in installed_apps:
        doc.disable_rounded_total = 1

    if not doc.is_return and not doc.is_debit_note:
        company_name = frappe.defaults.get_user_default("Company")
        company_doc = frappe.get_doc("Company", company_name)
        use_separate_sequence_for_credit_notes = None
        use_separate_sequence_for_sales_debit_notes = None
        if company_doc.custom_extended_details:
            extended_details = company_doc.custom_extended_details[0]
            use_separate_sequence_for_credit_notes = extended_details.use_separate_sequence_for_credit_notes
            use_separate_sequence_for_sales_debit_notes = extended_details.use_separate_sequence_for_sales_debit_notes

        meta = frappe.get_meta("Sales Invoice")
        naming_series_options = meta.get_field("naming_series").options
        series_list = [s.strip() for s in naming_series_options.split("\n") if s.strip()]

        if len(series_list) > 1:
            if not use_separate_sequence_for_credit_notes:
                sales_invoice_prefix = get_series_prefix(series_list[0])
                credit_note_prefix = get_series_prefix(series_list[1])
                row = frappe.db.sql(
                                        "SELECT current FROM `tabSeries` WHERE name = %s",
                                        (sales_invoice_prefix,)
                                    )
                current = row[0][0] if row else 0

                exists = frappe.db.sql(
                                        "SELECT name FROM `tabSeries` WHERE name = %s",
                                        (credit_note_prefix,)
                                    )
                if exists:
                    frappe.db.sql(
                                    "UPDATE `tabSeries` SET current = %s WHERE name = %s",
                                    (current, credit_note_prefix)
                                )
                else:
                     frappe.db.sql(
                                    "INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)",
                                    (credit_note_prefix, current)
                                )

        if len(series_list)> 2 and not use_separate_sequence_for_sales_debit_notes:
            sales_invoice_prefix = get_series_prefix(series_list[0])
            sale_debit_note_prefix = get_series_prefix(series_list[2])
            row = frappe.db.sql(
                                    "SELECT current FROM `tabSeries` WHERE name = %s",
                                        (sales_invoice_prefix,)
                                )
            current = row[0][0] if row else 0

            exists = frappe.db.sql(
                                    "SELECT name FROM `tabSeries` WHERE name = %s",
                                    (sale_debit_note_prefix,)
                                )
            if exists:
                frappe.db.sql(
                                "UPDATE `tabSeries` SET current = %s WHERE name = %s",
                                (current, sale_debit_note_prefix)
                            )
            else:
                    frappe.db.sql(
                                "INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)",
                                (sale_debit_note_prefix, current)
                            )