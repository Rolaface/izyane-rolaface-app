import frappe


def before_insert(doc, method):
    if doc.is_return == 1 or doc.is_debit_note == 1:
        sales_invoice = frappe.get_doc("Sales Invoice", doc.return_against) if doc.return_against else None
        payment_mode = (
            sales_invoice.custom_details[0].get("payment_mode")
            if sales_invoice and getattr(sales_invoice, "custom_details", None)
            else None
        )

        company_name = doc.company or frappe.defaults.get_user_default("Company")
        company_doc = frappe.get_doc("Company", company_name) if company_name and frappe.db.exists("Company", company_name) else None

        use_separate_sequence_for_credit_notes = None
        use_separate_sequence_for_sales_debit_notes = None
        if company_doc and getattr(company_doc, "custom_extended_details", None):
            use_separate_sequence_for_credit_notes = (
                company_doc.custom_extended_details[
                    0
                ].use_separate_sequence_for_credit_notes
            )
            use_separate_sequence_for_sales_debit_notes = (
                company_doc.custom_extended_details[
                    0
                ].use_separate_sequence_for_sales_debit_notes
            )

        if not doc.custom_details:
            doc.append("custom_details", {"payment_mode": payment_mode})
        else:
            doc.custom_details[0].payment_mode = payment_mode

        if sales_invoice:
            doc.currency = sales_invoice.currency

        # Credit note naming
        if doc.is_return == 1 and not doc.is_debit_note:
            naming_series_options = (
                frappe.get_meta("Sales Invoice").get_field("naming_series").options
            )
            series_list = [
                s.strip() for s in naming_series_options.split("\n") if s.strip()
            ]

            if len(series_list) < 2:
                frappe.throw("Please Configure Naming Series for Credit Notes.")

            doc.naming_series = series_list[1]

            if not use_separate_sequence_for_credit_notes:
                doc.flags.name_set = True
                doc.name = frappe.model.naming.make_autoname(series_list[1], doc=doc)

        elif doc.is_debit_note == 1:
            naming_series_options = frappe.get_meta("Sales Invoice").get_field("naming_series").options
            series_list = [
                s.strip() for s in naming_series_options.split("\n") if s.strip()
            ]
            if len(series_list) < 3:
                frappe.throw("Please Configure Naming Series for Sales Debit Note.")
            
            doc.naming_series = series_list[2]

            if not use_separate_sequence_for_sales_debit_notes:
                doc.flags.name_set = True
                doc.name = frappe.model.naming.make_autoname(series_list[2], doc=doc)

        frappe.log_error(
            title=f"Sales Invoice Debug - {doc.name}",
            message=frappe.as_json(doc.as_dict(), indent=4),
        )
