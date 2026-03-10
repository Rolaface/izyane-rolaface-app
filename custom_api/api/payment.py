import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from custom_api.utils.response import send_response

# ─────────────────────────────────────────
# RECEIVE PAYMENT (Customer → You)
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False)
def receive_payment():
    try:
        data = frappe.request.get_json()

        # Validate required fields
        required_fields = ["invoice_number", "payment_date", "payment_mode", "amount"]
        for field in required_fields:
            if not data.get(field):
                return send_response(
                    status="error",
                    message=f"'{field}' is required.",
                    data=None,
                    status_code=400,
                    http_status=400
                )

        invoice_number = data.get("invoice_number")
        payment_date = data.get("payment_date")
        payment_mode = data.get("payment_mode")
        amount = data.get("amount")
        reference_number = data.get("reference_number", "")
        deposit_into_account = data.get("deposit_into_account", "")
        customer_id = data.get("customer_id")
        customer_name = data.get("customer_name")

        # Resolve customer from customer_id if provided
        if customer_id:
            resolved = frappe.db.get_value(
                "Customer",
                {"custom_id": customer_id},
                "name"
            )
            if not resolved:
                return send_response(
                    status="error",
                    message=f"Customer with ID '{customer_id}' not found.",
                    data=None,
                    status_code=404,
                    http_status=404
                )
            customer_name = resolved

        # Validate invoice exists
        if not frappe.db.exists("Sales Invoice", invoice_number):
            return send_response(
                status="error",
                message=f"Sales Invoice '{invoice_number}' not found.",
                data=None,
                status_code=404,
                http_status=404
            )

        # Validate invoice belongs to customer
        if customer_name:
            invoice_customer = frappe.db.get_value("Sales Invoice", invoice_number, "customer")
            if invoice_customer != customer_name:
                return send_response(
                    status="error",
                    message="Invoice does not belong to this customer.",
                    data=None,
                    status_code=400,
                    http_status=400
                )

        # Validate amount vs outstanding
        outstanding = frappe.db.get_value("Sales Invoice", invoice_number, "outstanding_amount")
        if amount > outstanding:
            return send_response(
                status="error",
                message=f"Amount exceeds outstanding balance of {outstanding}.",
                data=None,
                status_code=400,
                http_status=400
            )

        # Use Frappe's built-in method
        pe = get_payment_entry("Sales Invoice", invoice_number)
        pe.mode_of_payment = payment_mode
        pe.posting_date = payment_date
        pe.reference_no = reference_number
        pe.reference_date = payment_date
        pe.paid_amount = amount
        pe.received_amount = amount

        if deposit_into_account:
            pe.paid_to = deposit_into_account

        for ref in pe.references:
            ref.allocated_amount = amount

        pe.insert(ignore_permissions=True)
        pe.submit()

        return send_response(
            status="success",
            message="Payment received successfully.",
            data={
                "paymentId": pe.name,
                "invoiceNumber": invoice_number,
                "customerName": customer_name,
                "amount": amount,
                "paymentMode": payment_mode,
                "paymentDate": payment_date,
                "status": pe.status
            },
            status_code=201,
            http_status=201
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Receive Payment API Error")
        return send_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )


# ─────────────────────────────────────────
# MAKE PAYMENT (You → Supplier)
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False)
def make_payment():
    try:
        data = frappe.request.get_json()

        # Validate required fields
        required_fields = ["supplier_id", "payment_date", "payment_mode", "amount"]
        for field in required_fields:
            if not data.get(field):
                return send_response(
                    status="error",
                    message=f"'{field}' is required.",
                    data=None,
                    status_code=400,
                    http_status=400
                )

        supplier_id = data.get("supplier_id")
        payment_date = data.get("payment_date")
        payment_mode = data.get("payment_mode")
        amount = data.get("amount")
        reference_number = data.get("reference_number", "")
        deposit_into_account = data.get("deposit_into_account", "")

        # Resolve supplier from supplier_id
        supplier_name = frappe.db.get_value(
            "Supplier",
            {"custom_supplier_id": supplier_id},
            "name"
        )
        if not supplier_name:
            return send_response(
                status="error",
                message=f"Supplier with ID '{supplier_id}' not found.",
                data=None,
                status_code=404,
                http_status=404
            )

        # Get default payable account
        default_payable_account = frappe.db.get_value(
            "Company",
            frappe.defaults.get_user_default("Company"),
            "default_payable_account"
        )

        # Get mode of payment account
        paid_from_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": payment_mode, "company": frappe.defaults.get_user_default("Company")},
            "default_account"
        ) or deposit_into_account

        if not paid_from_account:
            return send_response(
                status="error",
                message="Could not determine payment account. Please provide 'deposit_into_account'.",
                data=None,
                status_code=400,
                http_status=400
            )

        # Build Payment Entry manually (no invoice to link)
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Pay"
        pe.party_type = "Supplier"
        pe.party = supplier_name
        pe.posting_date = payment_date
        pe.mode_of_payment = payment_mode
        pe.paid_amount = amount
        pe.received_amount = amount
        pe.paid_from = paid_from_account
        pe.paid_to = default_payable_account
        pe.reference_no = reference_number
        pe.reference_date = payment_date

        pe.insert(ignore_permissions=True)
        pe.submit()

        return send_response(
            status="success",
            message="Payment made successfully.",
            data={
                "paymentId": pe.name,
                "supplierName": supplier_name,
                "amount": amount,
                "paymentMode": payment_mode,
                "paymentDate": payment_date,
                "status": pe.status
            },
            status_code=201,
            http_status=201
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Make Payment API Error")
        return send_response(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )