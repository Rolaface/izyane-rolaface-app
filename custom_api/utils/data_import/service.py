import frappe
from .utils import get_doctype_schema, extract_records_from_file

def get_import_template(doctype):
    return get_doctype_schema(doctype)

def process_bulk_import(doctype, records, row_offset=0):
    success_count = 0
    errors = []
    for index, row in enumerate(records):
        savepoint_name = f"import_row_{index}"
        frappe.db.savepoint(savepoint_name)
        try:
            doc_name = row.get("name")
            if doc_name and frappe.db.exists(doctype, doc_name):
                doc = frappe.get_doc(doctype, doc_name)
                doc.update(row)
                doc.save(ignore_permissions=True)
            else:
                row["doctype"] = doctype
                doc = frappe.get_doc(row)
                doc.insert(ignore_permissions=True)
            success_count += 1
        except Exception as e:
            frappe.db.rollback(save_point=savepoint_name)
            error_msg = str(e)
            if getattr(e, "message", None):
                error_msg = e.message
            errors.append({
                "row_index": index + row_offset,
                "row_data": row.get("item_code") or row.get("name") or str(row)[:50],
                "error": str(error_msg)
            })
    return success_count, errors

def process_file_import(doctype, filename, file_content):
    records = extract_records_from_file(filename, file_content)
    return process_bulk_import(doctype, records, row_offset=2)