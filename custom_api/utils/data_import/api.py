import frappe
from custom_api.utils.response import send_response
from .utils import validate_bulk_import_payload, validate_file_upload_payload
from ..party_utils import parse_api_payload
from . import service

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_import_schema(doctype):
    try:
        if not doctype:
            return send_response(status="fail", message="Doctype parameter is required.", status_code=400)
        if not frappe.db.exists("DocType", doctype):
            return send_response(status="fail", message=f"DocType '{doctype}' does not exist.", status_code=404)
        schema = service.get_import_template(doctype)
        return send_response(status="success", message=f"Schema retrieved for {doctype}", data=schema, status_code=200)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Import Schema API Error")
        return send_response(status="error", message=str(e), status_code=500)

@frappe.whitelist(allow_guest=False, methods=["POST"])
def bulk_create_records():
    try:
        data = parse_api_payload()
        validate_bulk_import_payload(data)
        doctype = data.get("doctype")
        records = data.get("data")
        success_count, errors = service.process_bulk_import(doctype, records)
        frappe.db.commit()
        if success_count == 0 and len(errors) > 0:
            final_status = "fail"
            msg = "All records failed to import."
        elif len(errors) > 0:
            final_status = "partial_success"
            msg = f"Imported {success_count} records, but {len(errors)} failed."
        else:
            final_status = "success"
            msg = f"Successfully imported all {success_count} records."
        return send_response(
            status=final_status,
            message=msg,
            data={"success_count": success_count, "error_count": len(errors), "errors": errors},
            status_code=207 if len(errors) > 0 else 200
        )
    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Bulk Import API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500)

@frappe.whitelist(allow_guest=False, methods=["POST"])
def import_from_file():
    try:
        doctype = frappe.form_dict.get("doctype")
        if "file" not in frappe.request.files:
            return send_response(status="fail", message="No file uploaded.", status_code=400)
        file_doc = frappe.request.files.get("file")
        validate_file_upload_payload(doctype, file_doc)
        success_count, errors = service.process_file_import(doctype, file_doc.filename, file_doc.read())
        frappe.db.commit()
        if success_count == 0 and len(errors) > 0:
            final_status = "fail"
            msg = "All records failed to import."
            status_code = 400
        elif len(errors) > 0:
            final_status = "partial_success"
            msg = f"Imported {success_count} records, but {len(errors)} failed."
            status_code = 207
        else:
            final_status = "success"
            msg = f"Successfully imported all {success_count} records."
            status_code = 200
        return send_response(
            status=final_status,
            message=msg,
            data={"success_count": success_count, "error_count": len(errors), "errors": errors},
            status_code=status_code,
            http_status=status_code
        )
    except frappe.exceptions.ValidationError as e:
        frappe.db.rollback()
        return send_response(status="fail", message=str(e), status_code=400, http_status=400)
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "File Import API Error")
        return send_response(status="error", message=f"Internal Server Error: {str(e)}", status_code=500, http_status=500)