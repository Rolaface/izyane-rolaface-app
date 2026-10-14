from custom_api.api.email_template.service import create_email_template_service
import frappe
from frappe.email.doctype.email_template.email_template import get_email_template
from custom_api.utils.response import send_old_response, send_response_list
from frappe.exceptions import DuplicateEntryError

TEMPLATE_TYPES = ["Sales Invoice", "Purchase Order", "Payment Entry", "Expense Claim", "Quotation","Customer Statement","Payment Reminder",
                  "Proforma Invoice"]

@frappe.whitelist(allow_guest=False, methods=["POST"])
def make_email_template(**payload):
        try:
            template_id = payload.get("id")
            doc_type = payload.get("doc_type")
            doc_type_name = payload.get("doc_type_name")
            get_full_doc = frappe.get_doc(doc_type, doc_type_name)
            response = get_email_template(template_id, get_full_doc.as_dict())
            return send_old_response(
                    status="success",
                    message=response,
                    status_code=200,
                    http_status=200
                )
        except Exception as e:
            frappe.log_error(str(e), "get email template by id API error")

            return send_old_response(
                                        status="fail",
                                        message=str(e),
                                        status_code=500,
                                        http_status=500
                                    )

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create():
    try:
        data = frappe.local.form_dict
        create_email_template_service(data)
        return send_old_response(
                                    status="success",
                                    message="Email Template created successfully",
                                    status_code=200,
                                    http_status=200
                                )
    except DuplicateEntryError as e:
        return send_old_response(
                                    status="fail",
                                    message="You Can only have one template for each Type. Please update the existing template if you want to make changes.",
                                    status_code=409,
                                    http_status=409
                                )
    except Exception as e:
        frappe.log_error(str(e), "get email template API error")

        return send_old_response(
                                    status="fail",
                                    message=str(e),
                                    status_code=500,
                                    http_status=500
                                )

@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update():
    try:
        data = frappe.local.form_dict

        template_name = data.get("id")

        if not template_name:
            return send_old_response(
                status="fail",
                message="template_name is required.",
                status_code=400,
                http_status=400,
            )

        if not frappe.db.exists("Email Template", template_name):
            return send_old_response(
                status="fail",
                message=f"Email Template '{template_name}' not found.",
                status_code=404,
                http_status=404,
            )

        template = frappe.get_doc("Email Template", template_name)

        if data.get("subject"):
            template.subject = data.get("subject")

        if data.get("message"):
            template.response = data.get("message")

        template.save(ignore_permissions=True)

        return send_old_response(
            status="success",
            message="Email Template updated successfully.",
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Email Template API Error")

        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500,
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_all():
    try:
        args = frappe.local.form_dict
        page = int(args.get("page", 1))
        page_size = int(args.get("pageSize", 10))
        search = args.get("search", "").strip() or None
        order_by = args.get("order_by", "creation desc")

        limit_start = (page - 1) * page_size

        or_filters = None

        if search:
            wildcard = f"%{search}%"
            or_filters = [
                ["name", "like", wildcard],
                ["subject", "like", wildcard],
            ]

        total = frappe.db.count("Email Template",
                                filters={"name": ["in", TEMPLATE_TYPES]}
                                )

        templates = frappe.db.get_all(
            "Email Template",
            or_filters = or_filters,
            filters = [["name", "in", TEMPLATE_TYPES]],
            fields = [
                "name as id",
                "subject",
                "response as message",
            ],
            order_by  = order_by,
            limit_start = limit_start,
            limit_page_length = page_size,
        )

        normalized = [t for t in templates]

        total_pages = max(1, -(-total // page_size))

        return send_old_response(
            status = "success",
            message = "Email Templates fetched successfully.",
            data = {
                "data": normalized,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            },
            status_code = 200,
            http_status = 200,
        )

    except Exception as e:
        frappe.log_error(str(e), "Get All Email Templates API Error")
        return send_old_response(
            status = "fail",
            message = str(e),
            status_code = 500,
            http_status = 500,
        )
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_by_id():
    try:
        template_name = frappe.request.args.get("id")
        template = frappe.get_doc("Email Template", template_name)
        data = {
                "id": template.name,
                "subject": template.subject,
                "message": template.response,
            }
        return send_old_response(
            status = "success",
            message = "Email Template fetched successfully.",
            data = data,
            status_code = 200,
            http_status = 200,
        )

    except Exception as e:
        frappe.log_error(str(e), "Get Email Template API Error")
        return send_old_response(
            status = "fail",
            message = str(e),
            status_code = 500,
            http_status = 500,
        )