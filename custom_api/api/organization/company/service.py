import frappe
from custom_api.api.organization.company.utlis.utils import build_company_response, map_company_update_fields
from mimetypes import guess_type
from frappe.utils.image import optimize_image
from frappe.utils import cint

def get_company_details():

    company_name = frappe.defaults.get_user_default("Company")

    if not company_name:
        frappe.throw("No default company set")

    company = frappe.get_doc("Company", company_name)

    return build_company_response(company)

def update_company_details(data):
    company_name = frappe.defaults.get_user_default("Company")

    if not company_name:
        frappe.throw("No default company set")

    company = frappe.get_doc("Company", company_name)

    map_company_update_fields(company, data)

    company.save(ignore_permissions=False)
    frappe.db.commit()

    return company.name

def remove_attach(doctype, docname, fieldname):
    old_file = frappe.get_value(
        "File",
        {
            "attached_to_doctype": doctype,
            "attached_to_name": docname,
            "attached_to_field": fieldname,
        },
        "name"
    )

    if old_file:
        frappe.delete_doc("File", old_file, ignore_permissions=True)

def upload_file(file, doctype, docname, fieldname, folder="Home", is_private=0, optimize=True):
	
	content = file.stream.read()
	filename = file.filename

	content_type = guess_type(filename)[0]
	if optimize and content_type and content_type.startswith("image/"):
		args = {"content": content, "content_type": content_type}
		if frappe.form_dict.max_width:
			args["max_width"] = int(frappe.form_dict.max_width)
		if frappe.form_dict.max_height:
			args["max_height"] = int(frappe.form_dict.max_height)
		content = optimize_image(**args)

	frappe.local.uploaded_file = content
	frappe.local.uploaded_filename = filename

	return frappe.get_doc(
			{
				"doctype": "File",
				"attached_to_doctype": doctype,
				"attached_to_name": docname,
				"attached_to_field": fieldname,
				"folder": folder,
				"file_name": filename,
				"is_private": cint(is_private),
				"content": content,
			}
		).save(ignore_permissions=True)
