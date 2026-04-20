from custom_api.utils.response import send_old_response
import frappe

@frappe.whitelist(allow_guest=False, methods=["GET"])
def summary():
    try:

        total_customers = frappe.db.count("Customer")

        total_individual = frappe.db.count("Customer", {"customer_type": "Individual"})

        total_company = frappe.db.count("Customer", {"customer_type": "Company"})
        
        tax_categories = frappe.db.get_all(
                            "Tax Category",
                            filters={"disabled": 0},
                            fields=["name"],
                            order_by="name asc",
                        )

        tax_category_counts = {}
        for tc in tax_categories:
            category_name = tc["name"]
            count = frappe.db.count("Customer", {"tax_category": category_name})
            tax_category_counts[category_name] = count

        tax_category_counts["noTaxCategoryCustomers"] = frappe.db.count(
            "Customer", {"tax_category": ["in", ["", None]]}
        )

        data = {
                "totalCustomers"          : total_customers,
                "totalIndividualCustomers": total_individual,
                "totalCompanyCustomers"   : total_company,
                **tax_category_counts,
                "taxCategories": [tc["name"] for tc in tax_categories],
            }

        return send_old_response(
            status="success",
            message="Customer dashboard retrieved successfully",
            data=data,
            status_code=200,
            http_status=200
        )

    except Exception as e:
        return send_old_response(
            status="error",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )