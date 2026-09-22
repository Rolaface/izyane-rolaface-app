import frappe
from custom_api.permission import require_permission
from custom_api.utils.response import send_old_response, send_response, send_response_list
from custom_api.api.payment.utils import PaymentEntryError
from custom_api.api.payment.service import (
    create_payment_entry_service,
    get_all_payments_service,
    get_ledger_account_service,
    get_payment_by_id_service,
    update_payment_entry_service,
)

def _rollback():
    if db := getattr(frappe.local, "db", None):
        db.rollback(chain=True)
    else:
        frappe.db.rollback()

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_ledger_account():
    try:
        payment_type = frappe.request.args.get("paymentType", "Pay")
        filter_param = frappe.request.args.get("filter", "to")
        txt = frappe.request.args.get("search", "")
        party_type = frappe.request.args.get("partyType", "Customer")

        response = get_ledger_account_service(payment_type, filter_param, txt, party_type)

        return send_old_response(
            status="success",
            message="Ledger accounts fetched successfully.",
            data=response,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Ledger Account API Error")
        return send_old_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["POST"])
@require_permission("Payment Entry", "create")
def create_payment_entry():
    try:
        data = frappe.request.get_json()

        pe_data = create_payment_entry_service(data)

        return send_old_response(
            status="success",
            message="Payment entry created successfully.",
            data=pe_data,
            status_code=201,
            http_status=201,
        )

    except PaymentEntryError as e:
        return send_old_response(
            status="error", message=e.message, data=None, status_code=e.status_code, http_status=e.status_code
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Payment Entry API Error")
        _rollback()

        return send_old_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["PUT"])
@require_permission("Payment Entry", "write")
def update_payment_entry():
    try:
        payment_id = frappe.request.args.get("id")
        data = frappe.request.get_json()

        if not payment_id:
            return send_old_response(
                status="error",
                message="Parameter 'id' is required.",
                data=None,
                status_code=400,
                http_status=400,
            )

        pe_data = update_payment_entry_service(payment_id, data)

        return send_old_response(
            status="success",
            message="Payment entry updated successfully.",
            data=pe_data,
            status_code=200,
            http_status=200,
        )

    except PaymentEntryError as e:
        return send_old_response(
            status="error", message=e.message, data=None, status_code=e.status_code, http_status=e.status_code
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Update Payment Entry API Error")
        _rollback()

        return send_old_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Payment Entry", "read")
def get_all_payments():
    try:
        args = frappe.request.args

        response_data = get_all_payments_service(args)

        if not response_data["payments"]:
            return send_response(
                status="success",
                message="No payments found.",
                data=[],
                status_code=200,
                http_status=200,
            )

        return send_response_list(
            status="success",
            message="Payments fetched successfully.",
            status_code=200,
            http_status=200,
            data=response_data,
        )

    except PaymentEntryError as e:
        return send_response(
            status="error", message=e.message, data=None, status_code=e.status_code, http_status=e.status_code
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Payments API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )

@frappe.whitelist(allow_guest=False, methods=["GET"])
@require_permission("Payment Entry", "read")
def get_payment_by_id():
    try:
        payment_id = frappe.request.args.get("id")

        if not payment_id:
            return send_response(
                status="error",
                message="Parameter 'payment_id' is required.",
                data=None,
                status_code=400,
                http_status=400,
            )

        detailed_data = get_payment_by_id_service(payment_id)

        return send_response(
            status="success",
            message="Payment Entry details fetched successfully.",
            data=detailed_data,
            status_code=200,
            http_status=200,
        )

    except PaymentEntryError as e:
        return send_response(
            status="error", message=e.message, data=None, status_code=e.status_code, http_status=e.status_code
        )

    except frappe.PermissionError:
        frappe.log_error(frappe.get_traceback(), "Get Payment By ID Permission Error")
        return send_response(
            status="error",
            message="You do not have permission to view this Payment Entry.",
            data=None,
            status_code=403,
            http_status=403,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Payment By ID API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )
