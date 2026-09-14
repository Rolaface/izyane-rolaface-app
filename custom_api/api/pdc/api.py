import frappe
from .service import get_all, create_pdc, update_pdc, delete_pdc
from custom_api.utils.response import send_old_response, send_response_list

@frappe.whitelist(allow_guest = False, methods=["GET"])
def get():
    try:
        data = frappe.local.form_dict

        pdc = get_all(data)

        return send_response_list(
                                    status="success",
                                    message="PDCs fetched successfully.",
                                    data=pdc,
                                    status_code=200,
                                    http_status=200,
                                )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get PDCs API Error")
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest = False, methods=["POST"])
def create():
    try:
        data = frappe.local.form_dict

        pdc_name = create_pdc(data)

        return send_old_response(
                    status="success",
                    message="PDC created successfully",
                    data={"name": pdc_name},
                    status_code=201,
                    http_status=201
                )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create PDC API Error")
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["PUT"])
def update(name):
    try:
        data = frappe.local.form_dict

        pdc_name = update_pdc(name,data)

        return send_old_response(
                    status="success",
                    message="PDC updated successfully",
                    data={"name": pdc_name},
                    status_code=200,
                    http_status=200
                )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update PDC API Error")
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete(name):
    try:
        if not frappe.db.exists("Custom Pdc Details", name):
            return send_old_response(
                status="fail",
                message="PDC not found",
                status_code=404,
                http_status=404
            )

        delete_pdc(name)

        return send_old_response(
                    status="success",
                    message="PDC deleted successfully",
                    data={"name": name},
                    status_code=200,
                    http_status=200
                )
    except frappe.exceptions.LinkExistsError:
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        return send_old_response(
            status="fail",
            message="Cannot delete: PDC is linked to existing transactions.",
            status_code=409,
            http_status=409
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Delete PDC API Error")
        if db := getattr(frappe.local, "db", None):
            db.rollback(chain=True)
        else:
            frappe.db.rollback()
        return send_old_response(
            status="fail",
            message=str(e),
            status_code=500,
            http_status=500
        )