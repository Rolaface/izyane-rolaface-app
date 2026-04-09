import frappe
def get_tax_account(company_name, root_type):
    """
    Fetch the default VAT/tax payable account for the company.
    """
    tax_account = frappe.db.get_value(
        "Account",
        {
            "company": company_name,
            "account_type": "Tax",
            "root_type": root_type,
            "is_group": 0
        },
        "name"
    )
    return tax_account