from erpnext.zra_client.custom_frappe_client import CustomFrappeClient
from erpnext.zra_client.generic_api import send_response
import frappe

CUSTOM_FRAPPE_INSTANCE = CustomFrappeClient()

def get_next_custom_supplier_id():
    last = frappe.db.sql(
        """
        SELECT custom_supplier_id
        FROM `tabSupplier`
        WHERE custom_supplier_id IS NOT NULL AND custom_supplier_id != ''
        ORDER BY CAST(custom_supplier_id AS UNSIGNED) DESC
        LIMIT 1
        """,
        as_dict=True
    )

    if last:
        return str(int(last[0].custom_supplier_id) + 1)
    else:
        return "1"
    
    
@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_suppliers():
    
    data = frappe.form_dict
    page = data.get("page", 1)
    page_size = data.get("page_size", 10)
    status = data.get("status")
    supplier_id = data.get("supplierId")
    page = int(page)
    page_size = int(page_size)
    start = (page - 1) * page_size


    filters = {}

    if status:
        filters["custom_status"] = status

    if supplier_id:
        filters["custom_supplier_id"] = supplier_id


    total = frappe.db.count("Supplier", filters=filters)

    total_pages = (total + page_size - 1) // page_size
    has_next = page < total_pages
    has_prev = page > 1
    suppliers = frappe.get_all(
        "Supplier",
        filters=filters,
        fields=[
            "name",
            "custom_supplier_id",
            "custom_status",
            "supplier_name",
            "tax_id",
            "default_currency",
            "mobile_no",
            "email_id",
            "custom_supplier_code",
            "tax_category",
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by="creation desc"
    )
    supplier_names = [s.get("name") for s in suppliers]

    all_invoices = frappe.get_all(
        "Purchase Invoice",
        filters={
            "supplier": ["in", supplier_names],
            "docstatus": 1
        },
        fields=["supplier", "outstanding_amount"]
    )
    outstanding_map = {}
    for inv in all_invoices:
        supplier = inv.get("supplier")
        outstanding_map[supplier] = (
            outstanding_map.get(supplier, 0) + (inv.get("outstanding_amount") or 0)
        )
    for i in suppliers:
        supplier_name = i.pop("name")
        i["supplierId"] = i.pop("custom_supplier_id")
        i["supplierCode"] = i.pop("custom_supplier_code")
        i["supplierName"] = i.pop("supplier_name")
        i["currency"] = i.pop("default_currency")
        i["emailId"] = i.pop("email_id")
        i["phoneNo"] = i.pop("mobile_no")
        i["tpin"] = i.pop("tax_id")
        i["taxCategory"] = i.pop("tax_category")
        i["status"] = i.pop("custom_status")
        i["totalOutstandingAmount"] = outstanding_map.get(supplier_name, 0)

    send_response(
        status="success",
        message="Suppliers fetched successfully",
        data={
            "suppliers": suppliers,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        },
        status_code=200,
        http_status=200
    )


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_supplier_details_id():
    
    data = frappe.form_dict
    custom_supplier_id = data.get("supplierId")
    
    if not custom_supplier_id:
        return send_response(
            status="error",
            message="Supplier ID is required",
            data={},
            status_code=400,
            http_status=400
        )
        
    supplier = frappe.db.get_value(
        "Supplier",
        {"custom_supplier_id": custom_supplier_id},
        "name"
    )
    
    if not custom_supplier_id:
        return send_response(
            status="error",
            message="Custom Supplier ID is required",
            data={},
            status_code=400,
            http_status=400
        )
    if not supplier:
        return send_response(
            status="error",
            message="Supplier not found",
            data={},
            status_code=404,
            http_status=404
        )

    supplier = frappe.get_doc("Supplier", supplier)
    supplier_details = {
        "supplierName": supplier.supplier_name,
        "supplierCode": supplier.custom_supplier_code,
        "supplierId": supplier.custom_supplier_id,
        "bankAccount": supplier.custom_bank_account,
        "accountHolder": supplier.custom_suppliers_account_holder_name,
        "dateOfAddition": supplier.custom_supplier_date_of_addition,
        "openingBalance": supplier.custom_supplier_opening_balance,
        "paymentTerms": supplier.custom_supplier_payment_terms,
        "branchAddress": supplier.custom_supplier_bank_address,
        "alternateNo": supplier.custom_supplier_alternate_no,
        "billingPostalCode": supplier.custom_supplier_postal_code,
        "swiftCode": supplier.custom_supplier_swift_code,
        "sortCode": supplier.custom_supplier_sort_code,
        "district": supplier.custom_supplier_district,
        "province": supplier.custom_supplier_province,
        "supplierCode": supplier.custom_supplier_code,
        "accountNumber": supplier.custom_account_no,
        "billingCity": supplier.custom_supplier_city,
        "currency": supplier.default_currency,
        "contactPerson": supplier.custom_supplier_contact_name,
        "billingAddressLine1": supplier.custom_supplier_address_line_1,
        "billingAddressLine2": supplier.custom_supplier_address_line_2,
        "phoneNo": supplier.mobile_no,
        "emailId": supplier.email_id,
        "billingCountry": supplier.country,
        "tpin": supplier.tax_id,
        "taxCategory": supplier.tax_category,
        "status": supplier.custom_status,
        "createdAt": supplier.creation,
        "updatedAt": supplier.modified
        
    }
    return send_response(
        status="success",
        message="Supplier details fetched successfully",
        data=supplier_details,
        status_code=200,
        http_status=200
    )

    
@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_supplier():
    data = frappe.form_dict

    custom_suppliers_account_holder_name = data.get("accountHolder")
    taxCategory = data.get("taxCategory")
    custom_supplier_date_of_addition = data.get("dateOfAddition")
    custom_supplier_opening_balance = data.get("openingBalance")
    custom_supplier_payment_terms = data.get("paymentTerms")
    custom_supplier_bank_address = data.get("branchAddress")
    custom_supplier_alternate_no = data.get("alternateNo")
    custom_supplier_postal_code = data.get("billingPostalCode")
    custom_supplier_swift_code = data.get("swiftCode")
    custom_supplier_sort_code = data.get("sortCode")
    supplier_primary_contact = data.get("contactPerson")
    custom_supplier_address_line_1 = data.get("billingAddressLine1")
    custom_supplier_address_line_2 = data.get("billingAddressLine2")
    custom_supplier_district = data.get("district")
    custom_supplier_province = data.get("province")
    custom_supplier_code = data.get("supplierCode")
    custom_account_no = data.get("accountNumber")
    custom_supplier_city = data.get("billingCity")
    default_currency = data.get("currency")
    supplier_name = data.get("supplierName")
    tax_id = data.get("tpin")
    mobile_no = data.get("phoneNo")
    email_id = data.get("emailId")
    bankAccount = data.get("bankAccount")
    country = data.get("billingCountry")
    status = data.get("status", "Active")

    if not supplier_name:
        return send_response(status="fail", message="supplierName is required", status_code=400, http_status=400)

    if not tax_id:
        return send_response(status="fail", message="Supplier TPIN is required", status_code=400, http_status=400)
    
    # if tax_id and len(tax_id) != 10:
    #     return send_response(
    #         status="fail",
    #         message="Supplier TPIN must be exactly 10 characters long",
    #         status_code=400,
    #         http_status=400
    #     )
        
    if tax_id and not tax_id.isalnum():
        return send_response(
            status="fail",
            message= "Supplier TPIN must be alphanumeric",
            status_code=400,
            http_status=400
        )
        
    

    if not email_id:
        return send_response(
            status="fail", 
            message="email_id is required", 
            status_code=400, 
            http_status= 400
        )

    if frappe.db.exists("Supplier", {"tax_id": tax_id}):
        return send_response(
            status="fail",
            message=f"Supplier with TPIN '{tax_id}' already exists",
            status_code=400,
            http_status=400
        )

    if "@" not in email_id or "." not in email_id:
        return send_response(
            status="fail",
            message="Invalid email format",
            status_code=400,
            http_status=400
        )

    if frappe.db.exists("Supplier", {"email_id": email_id}):
        return send_response(
            status="fail",
            message=f"Supplier with email '{email_id}' already exists",
            status_code=400,
            http_status=400
        )

    if frappe.db.exists("Supplier", {"supplier_name": supplier_name}):
        return send_response(
            status="fail",
            message=f"Supplier with name '{supplier_name}' already exists",
            status_code=400,
            http_status=400
        )

    TAX_CAT = CUSTOM_FRAPPE_INSTANCE.GetAvailableTaxCategory()

    if taxCategory not in TAX_CAT:
        return send_response(
            status="fail",
            message=f"Tax Category '{taxCategory}' does not exist.  Available Tax Categories : {TAX_CAT}",
            data=[],
            status_code=400,
            http_status=400
        ) 
    supplier_id = get_next_custom_supplier_id()

    try:
        supplier = frappe.get_doc({
            "doctype": "Supplier",
            "supplier_name": supplier_name,
            "custom_suppliers_account_holder_name": custom_suppliers_account_holder_name,
            "custom_supplier_date_of_addition": custom_supplier_date_of_addition,
            "custom_supplier_opening_balance": custom_supplier_opening_balance,
            "custom_supplier_payment_terms": custom_supplier_payment_terms,
            "custom_supplier_bank_address": custom_supplier_bank_address,
            "custom_supplier_alternate_no": custom_supplier_alternate_no,
            "custom_supplier_postal_code": custom_supplier_postal_code,
            "custom_supplier_swift_code": custom_supplier_swift_code,
            "custom_supplier_sort_code": custom_supplier_sort_code,
            "custom_supplier_contact_name": supplier_primary_contact,
            "custom_supplier_address_line_1": custom_supplier_address_line_1,
            "custom_supplier_address_line_2": custom_supplier_address_line_2,
            "custom_supplier_district": custom_supplier_district,
            "custom_supplier_province": custom_supplier_province,
            "custom_supplier_code": custom_supplier_code,
            "custom_account_no": custom_account_no,
            "custom_supplier_city": custom_supplier_city,
            "default_currency": default_currency,
            "custom_supplier_id": supplier_id,
            "tax_category": taxCategory,
            "mobile_no": mobile_no,
            "email_id": email_id,
            "custom_bank_account": bankAccount,
            "country": country,
            "tax_id": tax_id,
            "custom_status": status
        })

        supplier.insert()
        frappe.db.commit()

        return send_response(
            status="success",
            message="Supplier created successfully",
            data={},
            status_code=201,
            http_status=201
        )

    except Exception as e:
        return send_response(
            status="error",
            message=f"Error creating supplier: {str(e)}",
            data={},
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["PATCH"])
def update_supplier():
    data = frappe.form_dict


    supplier_id = data.get("supplierId")
    if not supplier_id:
        return send_response(
            status="fail",
            message="supplierId is required",
            status_code=400,
            http_status=400
        )

    supplier_name = frappe.db.get_value(
        "Supplier",
        {"custom_supplier_id": supplier_id},
        "name"
    )

    if not supplier_name:
        return send_response(
            status="fail",
            message="Supplier not found",
            status_code=404,
            http_status=404
        )

    supplier = frappe.get_doc("Supplier", supplier_name)
    custom_suppliers_account_holder_name = data.get("accountHolder")
    custom_supplier_date_of_addition = data.get("dateOfAddition")
    custom_supplier_opening_balance = data.get("openingBalance")
    custom_supplier_payment_terms = data.get("paymentTerms")
    custom_supplier_bank_address = data.get("branchAddress")
    custom_supplier_alternate_no = data.get("alternateNo")
    custom_supplier_postal_code = data.get("billingPostalCode")
    custom_supplier_swift_code = data.get("swiftCode")
    custom_supplier_sort_code = data.get("sortCode")
    supplier_primary_contact = data.get("contactPerson")
    custom_supplier_address_line_1 = data.get("billingAddressLine1")
    custom_supplier_address_line_2 = data.get("billingAddressLine2")
    custom_supplier_district = data.get("district")
    custom_supplier_province = data.get("province")
    custom_supplier_code = data.get("supplierCode")
    custom_account_no = data.get("accountNumber")
    custom_supplier_city = data.get("billingCity")
    default_currency = data.get("currency")
    supplier_name_input = data.get("supplierName")
    tax_id = data.get("tpin")
    mobile_no = data.get("phoneNo")
    email_id = data.get("emailId")
    bank_account = data.get("bankAccount")
    country = data.get("billingCountry")
    taxCategory = data.get("taxCategory")
    status = data.get("status")
    
    print('Mobile No:', mobile_no)

    if supplier_name_input:
        if (
            supplier_name_input != supplier.supplier_name
            and frappe.db.exists("Supplier", {"supplier_name": supplier_name_input})
        ):
            return send_response(
                status="fail",
                message=f"Supplier with name '{supplier_name_input}' already exists",
                status_code=400,
                http_status=400
            )
    if tax_id:
        tax_id = tax_id.strip()

        if not tax_id.isdigit():
            return send_response(
                status="fail",
                message="Supplier TPIN must be numeric digits",
                status_code=400,
                http_status=400
            )

        if tax_id != supplier.tax_id and frappe.db.exists(
            "Supplier", {"tax_id": tax_id}
        ):
            return send_response(
                status="fail",
                message=f"Supplier with TPIN '{tax_id}' already exists",
                status_code=400,
                http_status=400
            )

    if email_id:
        if "@" not in email_id or "." not in email_id:
            return send_response(
                status="fail",
                message="Invalid email format",
                status_code=400,
                http_status=400
            )
    
    TAX_CAT = CUSTOM_FRAPPE_INSTANCE.GetAvailableTaxCategory()    
    if taxCategory not in TAX_CAT:
        return send_response(
            status="fail",
            message=f"Tax Category '{taxCategory}' does not exist.  Available Tax Categories : {TAX_CAT}",
            data=[],
            status_code=400,
            http_status=400
        ) 

    if custom_suppliers_account_holder_name is not None:
        supplier.custom_suppliers_account_holder_name = custom_suppliers_account_holder_name

    if custom_supplier_date_of_addition is not None:
        supplier.custom_supplier_date_of_addition = custom_supplier_date_of_addition

    if custom_supplier_opening_balance is not None:
        supplier.custom_supplier_opening_balance = custom_supplier_opening_balance

    if custom_supplier_payment_terms is not None:
        supplier.custom_supplier_payment_terms = custom_supplier_payment_terms

    if custom_supplier_bank_address is not None:
        supplier.custom_supplier_bank_address = custom_supplier_bank_address

    if custom_supplier_alternate_no is not None:
        supplier.custom_supplier_alternate_no = custom_supplier_alternate_no

    if custom_supplier_postal_code is not None:
        supplier.custom_supplier_postal_code = custom_supplier_postal_code

    if custom_supplier_swift_code is not None:
        supplier.custom_supplier_swift_code = custom_supplier_swift_code

    if custom_supplier_sort_code is not None:
        supplier.custom_supplier_sort_code = custom_supplier_sort_code

    if supplier_primary_contact is not None:
        supplier.custom_supplier_contact_name = supplier_primary_contact

    if custom_supplier_address_line_1 is not None:
        supplier.custom_supplier_address_line_1 = custom_supplier_address_line_1

    if custom_supplier_address_line_2 is not None:
        supplier.custom_supplier_address_line_2 = custom_supplier_address_line_2

    if custom_supplier_district is not None:
        supplier.custom_supplier_district = custom_supplier_district

    if custom_supplier_province is not None:
        supplier.custom_supplier_province = custom_supplier_province

    if custom_supplier_code is not None:
        supplier.custom_supplier_code = custom_supplier_code

    if custom_account_no is not None:
        supplier.custom_account_no = custom_account_no

    if custom_supplier_city is not None:
        supplier.custom_supplier_city = custom_supplier_city

    if default_currency is not None:
        supplier.default_currency = default_currency
        
    if bank_account is not None:
        supplier.custom_bank_account = bank_account

    if country is not None:
        supplier.country = country

    if status is not None:
        supplier.custom_status = status
        
    if taxCategory is not None:
        supplier.tax_category = taxCategory
        

    if tax_id is not None:
        supplier.tax_id = tax_id

    if supplier_name_input and supplier_name_input != supplier.supplier_name:
        frappe.rename_doc(
            "Supplier",
            supplier.name,
            supplier_name_input,
            force=True
        )
        supplier = frappe.get_doc("Supplier", supplier_name_input)


    if email_id:
        contact_name = frappe.db.get_value(
            "Dynamic Link",
            {
                "link_doctype": "Supplier",
                "link_name": supplier.name,
                "parenttype": "Contact"
            },
            "parent"
        )

        if contact_name:
            contact = frappe.get_doc("Contact", contact_name)
        else:
            contact = frappe.new_doc("Contact")
            contact.first_name = supplier.supplier_name
            contact.append("links", {
                "link_doctype": "Supplier",
                "link_name": supplier.name
            })

        if email_id:
            contact.email_ids = []
            contact.append("email_ids", {
                "email_id": email_id,
                "is_primary": 1
            })

        contact.save(ignore_permissions=True)

    try:
        supplier.save(ignore_permissions=True)
        if mobile_no:
            frappe.db.sql("""
                UPDATE `tabSupplier`
                SET mobile_no = %s
                WHERE name = %s
            """, (mobile_no, supplier_name))
        frappe.db.commit()

        return send_response(
            status="success",
            message="Supplier updated successfully",
            data=[],
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Supplier Error")
        return send_response(
            status="error",
            message=str(e),
            data={},
            status_code=500,
            http_status=500
        )



@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_supplier():
    data = frappe.form_dict
    custom_supplier_id = data.get("supplierId")

    if not custom_supplier_id:
        return send_response(
            status="error",
            message="supplierId is required",
            data={},
            status_code=400,
            http_status=400
        )

    supplier_name = frappe.db.get_value(
        "Supplier",
        {"custom_supplier_id": custom_supplier_id},
        "name"
    )

    if not supplier_name:
        return send_response(
            status="error",
            message="Supplier not found",
            data={},
            status_code=404,
            http_status=404
        )

    try:
        frappe.delete_doc("Supplier", supplier_name, force=True)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Supplier deleted successfully",
            data={"supplierId": custom_supplier_id},
            status_code=200,
            http_status=200
        )

    except Exception as e:
        return send_response(
            status="error",
            message=f"Error deleting supplier: {str(e)}",
            data={},
            status_code=500,
            http_status=500
        )

    
