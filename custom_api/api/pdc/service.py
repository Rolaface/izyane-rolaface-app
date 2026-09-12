from custom_api.api.organization.company.service import upload_file

from .utils import build_pi_filters
import frappe

def get_all(data):
    or_filters = []
    filters = build_pi_filters(data)
    order_by = data.get("order_by", "creation desc")
    page = int(data.get("page", 1))
    search = data.get("search", "").strip()
    if search:
            or_filters = [
                ["document_name", "like", f"%{search}%"],
                ["cheque_reference_number", "like", f"%{search}%"],
                ["cheque_date", "like", f"%{search}%"],
                ["amount", "like", f"%{search}%"]
            ]
    page_size = int(data.get("page_size", 20))
    limit_start = (page - 1) * page_size
    pdcs = frappe.get_all(
                            "Custom Pdc Details",
                            filters=filters,
                            or_filters=or_filters,
                            fields=["name","document_name", "cheque_reference_number", "cheque_date", "amount", "status", "attachment"],
                            order_by=order_by,
                            limit_start=limit_start,
                            limit_page_length=page_size
                            )
    total_count = frappe.db.count("Custom Pdc Details", filters=filters)

    return {
            "data": pdcs,
            "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total_count,
                    "total_pages": max(1, (total_count + page_size - 1) // page_size),
                    "has_next": page < total_count,
                    "has_prev": page > 1
                }
        }

def create_pdc(data):
    pdc_doc = frappe.get_doc({
                                "doctype": "Custom Pdc Details",
                                "document_type": data.get("document_type"),
                                "document_name": data.get("document_name"),
                                "cheque_reference_number": data.get("cheque_reference_number"),
                                "cheque_date": data.get("cheque_date"),
                                "amount": data.get("amount"),
                                "status": data.get("status", "Unused")
                            })
    pdc_doc.insert()

    attachment_file = frappe.local.request.files.get("attachment")
    if attachment_file:
        uploaded = upload_file(attachment_file, "Custom Pdc Details", pdc_doc.name, "attachment")
        pdc_doc.attachment = uploaded.file_url
        pdc_doc.save()

    return pdc_doc.name
