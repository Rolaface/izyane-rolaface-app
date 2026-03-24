from erpnext.zra_client.generic_api import send_response_list
import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from custom_api.utils.response import send_response
from frappe.desk.search import search_widget
from erpnext.zra_client.generic_api import send_response as old_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_ledger_account():
    try:
        payment_type = frappe.request.args.get("paymentType", "Pay")
        filter = frappe.request.args.get("filter", "to")
        txt = frappe.request.args.get("search","")
        company = frappe.defaults.get_user_default("Company")

        from_filters = {"account_type":["in",["Bank","Cash"]],"is_group":0,"company":f"{company}"}
        to_filters = {"account_type":["in",["Payable"]],"is_group":0,"company":f"{company}"}

        if payment_type == "Pay" and filter == "from":
            filters = from_filters

        if payment_type == "Pay" and filter == "to":
            filters = to_filters

        if payment_type == "Receive" and filter == "to":
            filters = from_filters

        if payment_type == "Receive" and filter == "from":
            filters = to_filters

        response = search_widget(
                "Account",
                txt.strip(),
                None,
                searchfield=None,
                page_length=10,
                filters=filters,
                filter_fields='["account_currency"]',
                reference_doctype="Payment Entry",
                ignore_user_permissions=0,
                as_dict= True,

            )
        return old_response(
            status="success",
            message="Suppliers fetched successfully.",
            data= response,
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Suppliers API Error")
        return old_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


# ─────────────────────────────────────────
# RECEIVE PAYMENT (Customer → You)
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False, methods=["POST"])
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
                    http_status=400,
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
                "Customer", {"custom_id": customer_id}, "name"
            )
            if not resolved:
                return send_response(
                    status="error",
                    message=f"Customer with ID '{customer_id}' not found.",
                    data=None,
                    status_code=404,
                    http_status=404,
                )
            customer_name = resolved

        # Validate invoice exists
        if not frappe.db.exists("Sales Invoice", invoice_number):
            return send_response(
                status="error",
                message=f"Sales Invoice '{invoice_number}' not found.",
                data=None,
                status_code=404,
                http_status=404,
            )

        # Validate invoice belongs to customer
        if customer_name:
            invoice_customer = frappe.db.get_value(
                "Sales Invoice", invoice_number, "customer"
            )
            if invoice_customer != customer_name:
                return send_response(
                    status="error",
                    message="Invoice does not belong to this customer.",
                    data=None,
                    status_code=400,
                    http_status=400,
                )

        # Validate amount vs outstanding
        outstanding = frappe.db.get_value(
            "Sales Invoice", invoice_number, "outstanding_amount"
        )
        if amount > outstanding:
            return send_response(
                status="error",
                message=f"Amount exceeds outstanding balance of {outstanding}.",
                data=None,
                status_code=400,
                http_status=400,
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
                "status": pe.status,
            },
            status_code=201,
            http_status=201,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Receive Payment API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


# ─────────────────────────────────────────
# MAKE PAYMENT (You → Supplier)
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False, methods=["POST"])
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
                    http_status=400,
                )

        supplier_id = data.get("supplier_id")
        payment_date = data.get("payment_date")
        payment_mode = data.get("payment_mode")
        amount = data.get("amount")
        reference_number = data.get("reference_number", "")
        deposit_into_account = data.get("deposit_into_account", "")

        # Resolve supplier from supplier_id
        supplier_name = frappe.db.get_value(
            "Supplier", {"custom_supplier_id": supplier_id}, "name"
        )
        if not supplier_name:
            return send_response(
                status="error",
                message=f"Supplier with ID '{supplier_id}' not found.",
                data=None,
                status_code=404,
                http_status=404,
            )

        # Get default payable account
        default_payable_account = frappe.db.get_value(
            "Company",
            frappe.defaults.get_user_default("Company"),
            "default_payable_account",
        )

        # Get mode of payment account
        paid_from_account = (
            frappe.db.get_value(
                "Mode of Payment Account",
                {
                    "parent": payment_mode,
                    "company": frappe.defaults.get_user_default("Company"),
                },
                "default_account",
            )
            or deposit_into_account
        )

        if not paid_from_account:
            return send_response(
                status="error",
                message="Could not determine payment account. Please provide 'deposit_into_account'.",
                data=None,
                status_code=400,
                http_status=400,
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
                "status": pe.status,
            },
            status_code=201,
            http_status=201,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Make Payment API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


# ─────────────────────────────────────────
# GET ALL PAYMENTS
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_all_payments():
    try:
        args = frappe.request.args

        page = args.get("page", 1)
        page_size = args.get("page_size", 10)

        try:
            page = int(page)
            if page < 1:
                raise ValueError
        except ValueError:
            return send_response(
                status="error",
                message="'page' must be a positive integer.",
                data=None,
                status_code=400,
                http_status=400,
            )

        try:
            page_size = int(page_size)
            if page_size < 1:
                raise ValueError
        except ValueError:
            return send_response(
                status="error",
                message="'page_size' must be a positive integer.",
                data=None,
                status_code=400,
                http_status=400,
            )

        start_index = (page - 1) * page_size

        # ─────────────────────────────────────────
        # FILTERS
        # ─────────────────────────────────────────
        filters = {}
        or_filters = []

        payment_type = args.get("paymentType")
        if payment_type:
            payment_type = payment_type.lower()
            if payment_type == "receive":
                filters["payment_type"] = "Receive"
            elif payment_type == "pay":
                filters["payment_type"] = "Pay"

        # Party filter (Customer or Supplier)
        party_type = args.get("partyType")
        if party_type:
            filters["party_type"] = party_type

        party_id = args.get("CustomerId")
        party_type = args.get("partyType")  # "Customer" or "Supplier"
        if party_id and party_type:
            if party_type == "Customer":
                party_name = frappe.db.get_value(
                    "Customer", {"custom_id": party_id}, "name"
                )
            elif party_type == "Supplier":
                party_name = frappe.db.get_value(
                    "Supplier", {"custom_id": party_id}, "name"
                )
            else:
                party_name = None

            if not party_name:
                return send_response(
                    status="error",
                    message=f"{party_type} with ID '{party_id}' not found.",
                    data=None,
                    status_code=404,
                    http_status=404,
                )
            filters["party_type"] = party_type
            filters["party"] = party_name

        # Payment mode filter
        payment_mode = args.get("paymentMode")
        if payment_mode:
            filters["mode_of_payment"] = ["like", f"%{payment_mode}%"]

        # Status filter
        status = args.get("status")
        if status:
            filters["status"] = status

        # Date range filter
        from_date = args.get("from_date")
        to_date = args.get("to_date")
        if from_date and to_date:
            filters["posting_date"] = ["between", [from_date, to_date]]
        elif from_date:
            filters["posting_date"] = [">=", from_date]
        elif to_date:
            filters["posting_date"] = ["<=", to_date]

        # Amount range filter
        min_amount = args.get("minAmount")
        max_amount = args.get("maxAmount")
        if min_amount and max_amount:
            filters["paid_amount"] = ["between", [float(min_amount), float(max_amount)]]
        elif min_amount:
            filters["paid_amount"] = [">=", float(min_amount)]
        elif max_amount:
            filters["paid_amount"] = ["<=", float(max_amount)]

        # Search filter
        search = args.get("search")
        if search:
            or_filters = [
                ["name", "like", f"%{search}%"],
                ["party", "like", f"%{search}%"],
                ["mode_of_payment", "like", f"%{search}%"],
                ["reference_no", "like", f"%{search}%"],
            ]

            try:
                search_amount = float(search)
                or_filters.append(["paid_amount", "=", search_amount])
            except ValueError:
                pass

            # Search by date if valid date
            from datetime import datetime

            try:
                datetime.strptime(search, "%Y-%m-%d")
                or_filters.append(["posting_date", "=", search])
            except ValueError:
                pass

        # ─────────────────────────────────────────
        # SORTING
        # ─────────────────────────────────────────
        allowed_sort_fields = {
            "id": "name",
            "partyName": "party",
            "paymentDate": "posting_date",
            "amount": "paid_amount",
            "paymentMode": "mode_of_payment",
            "status": "status",
        }

        sort_by = args.get("sortBy", "paymentDate")
        sort_order = args.get("sortOrder", "desc").lower()
        sort_field = allowed_sort_fields.get(sort_by, "posting_date")
        sort_order = "asc" if sort_order == "asc" else "desc"
        order_by = f"{sort_field} {sort_order}"

        # ─────────────────────────────────────────
        # FETCH
        # ─────────────────────────────────────────
        payments = frappe.get_all(
            "Payment Entry",
            filters=filters,
            or_filters=or_filters,
            fields=[
                "name as paymentId",
                "payment_type as paymentType",
                "party_type as partyType",
                "party as partyName",
                "mode_of_payment as paymentMode",
                "posting_date as paymentDate",
                "paid_amount as amount",
                "reference_no as referenceNumber",
                "status",
            ],
            order_by=order_by,
            start=start_index,
            page_length=page_size,
        )

        total_payments = len(
            frappe.get_all(
                "Payment Entry", filters=filters, or_filters=or_filters, pluck="name"
            )
        )

        if total_payments == 0:
            return send_response(
                status="success",
                message="No payments found.",
                data=[],
                status_code=200,
                http_status=200,
            )

        total_pages = (total_payments + page_size - 1) // page_size

        response_data = {
            "payments": payments,
            "pagination": {
                "page": page,
                "pageSize": page_size,
                "total": total_payments,
                "totalPages": total_pages,
                "hasNext": page < total_pages,
                "hasPrev": page > 1,
            },
        }

        return send_response_list(
            status="success",
            message="Payments fetched successfully.",
            status_code=200,
            http_status=200,
            data=response_data,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get All Payments API Error")
        return send_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


# ─────────────────────────────────────────
# GET PAYMENT BY ID
# ─────────────────────────────────────────
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_payment_by_id():
    try:
        payment_id = frappe.request.args.get("payment_id")

        if not payment_id:
            return send_response(
                status="error",
                message="Parameter 'payment_id' is required.",
                data=None,
                status_code=400,
                http_status=400,
            )

        if not frappe.db.exists("Payment Entry", payment_id):
            return send_response(
                status="error",
                message=f"Payment Entry '{payment_id}' not found.",
                data=None,
                status_code=404,
                http_status=404,
            )

        doc = frappe.get_doc("Payment Entry", payment_id)

        # 1. Map Allocations (References)
        allocations = []
        for ref in doc.get("references"):
            allocations.append(
                {
                    "reference_doctype": ref.reference_doctype,
                    "reference_name": ref.reference_name,
                    "total_amount": ref.total_amount,
                    "outstanding_amount": ref.outstanding_amount,
                    "allocated_amount": ref.allocated_amount,
                    "account": ref.account,
                }
            )

        # 2. Map Taxes
        taxes = []
        for t in doc.get("taxes"):
            taxes.append(
                {
                    "account_head": t.account_head,
                    "tax_amount": t.tax_amount,
                    "description": t.description,
                    "rate": t.rate,
                }
            )

        # 3. Map Deductions
        deductions = []
        for d in doc.get("deductions"):
            deductions.append(
                {"account": d.account, "amount": d.amount, "description": d.description}
            )

        detailed_data = {
            "header": {
                "payment_id": doc.name,
                "payment_type": doc.payment_type,
                "status": doc.status,
                "posting_date": doc.posting_date,
                "company": doc.company,
                "naming_series": doc.naming_series,
            },
            "party_info": {
                "party_type": doc.party_type,
                "party": doc.party,
                "party_name": doc.party_name,
                "contact_person": doc.contact_person,
                "contact_email": doc.contact_email,
            },
            "transaction_info": {
                "mode_of_payment": doc.mode_of_payment,
                "paid_from": doc.paid_from,
                "paid_from_currency": doc.paid_from_account_currency,
                "paid_to": doc.paid_to,
                "paid_to_currency": doc.paid_to_account_currency,
                "bank": doc.bank,
                "bank_account_no": doc.bank_account_no,
                "party_bank_account": doc.party_bank_account,
                "reference_no": doc.reference_no,
                "reference_date": doc.reference_date,
                "clearance_date": doc.clearance_date,
                "cost_center": doc.cost_center,
                "project": doc.project,
            },
            "amounts": {
                "paid_amount": doc.paid_amount,
                "received_amount": doc.received_amount,
                "base_paid_amount": doc.base_paid_amount,
                "base_received_amount": doc.base_received_amount,
                "total_allocated_amount": doc.total_allocated_amount,
                "unallocated_amount": doc.unallocated_amount,
                "difference_amount": doc.difference_amount,
                "source_exchange_rate": doc.source_exchange_rate,
                "target_exchange_rate": doc.target_exchange_rate,
                "amount_in_words": doc.in_words,
            },
            "allocations": allocations,
            "taxes": taxes,
            "deductions": deductions,
            "remarks": doc.remarks,
        }

        return send_response(
            status="success",
            message="Payment Entry details fetched successfully.",
            data=detailed_data,
            status_code=200,
            http_status=200,
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
