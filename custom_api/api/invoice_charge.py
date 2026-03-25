import math
import frappe
from custom_api.utils.response import send_response


def _get_arg(key, default=None):
    return frappe.request.args.get(key, default)


def _get_request_data():
    try:
        if frappe.request and getattr(frappe.request, "data", None):
            data_str = frappe.request.data.decode("utf-8")
            return frappe.parse_json(data_str)
    except Exception:
        pass
    return frappe.local.form_dict or {}


def _make_name(invoice, charge_type):
    safe_charge = str(charge_type).replace(" ", "_").lower().strip()
    return f"{str(invoice).strip()}-{safe_charge}"


def _format_doc(doc):
    return {
        "id": str(doc.name),
        "invoice": str(doc.invoice),
        "charge_type": str(doc.charge_type),
        "amount": float(doc.amount or 0.0),
        "timestamps": {
            "created_at": doc.creation,
            "modified_at": doc.modified,
        },
    }


@frappe.whitelist(methods=["GET"])
def get_invoice_charges():
    try:
        invoice_raw = _get_arg("invoice")
        invoice = str(invoice_raw).strip() if invoice_raw else None
        search = str(_get_arg("search", "")).strip().lower()
        page = max(1, int(_get_arg("page", 1)))
        page_size = max(1, int(_get_arg("page_size", 50)))

        start = (page - 1) * page_size

        filters = {}
        if invoice:
            filters["invoice"] = invoice

        or_filters = []
        if search:
            or_filters = [
                ["name", "like", f"%{search}%"],
                ["charge_type", "like", f"%{search}%"],
            ]

        count_result = frappe.get_all(
            "Invoice Charge",
            filters=filters,
            or_filters=or_filters,
            fields=["count(name) as total_count"],
        )

        total_items = count_result[0].get("total_count", 0) if count_result else 0

        rows = frappe.get_all(
            "Invoice Charge",
            filters=filters,
            or_filters=or_filters,
            fields=["name", "invoice", "charge_type", "amount", "creation", "modified"],
            order_by="creation desc",
            limit_start=start,
            limit_page_length=page_size,
        )

        data = [
            {
                "id": str(r.name),
                "invoice": str(r.invoice),
                "charge_type": str(r.charge_type),
                "amount": float(r.amount or 0.0),
                "created_at": r.creation,
                "modified_at": r.modified,
            }
            for r in rows
        ]

        total_pages = math.ceil(total_items / page_size)

        pagination = {
            "page": page,
            "page_size": page_size,
            "items_in_page": len(data),
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

        return send_response(
            status="success",
            message="Invoice charges fetched successfully.",
            data={"data": data, "pagination": pagination},
        )
    except Exception as e:
        return send_response("error", str(e), status_code=500)


@frappe.whitelist(methods=["GET"])
def get_invoice_charge(id):
    try:
        record_id = str(id).strip() if id is not None else ""
        if not record_id:
            return send_response("error", "ID is required", status_code=400)

        if not frappe.db.exists("Invoice Charge", record_id):
            return send_response("error", "Record not found", status_code=404)

        doc = frappe.get_doc("Invoice Charge", record_id)

        return send_response(
            status="success",
            message="Record fetched successfully.",
            data=_format_doc(doc),
        )
    except Exception as e:
        return send_response("error", str(e), status_code=500)


def process_and_insert_charges(invoice_name, charges_list):
    validated = []
    processed_names = set()
    results = []

    for charge in charges_list:
        charge_type = str(charge.get("charge_type", "")).strip()
        amount_raw = charge.get("amount")

        if not charge_type or amount_raw is None:
            frappe.throw("charge_type and amount are required")

        try:
            amount = float(amount_raw)
        except ValueError:
            frappe.throw(f"Invalid amount for {charge_type}")

        name = _make_name(invoice_name, charge_type)

        if name in processed_names:
            frappe.throw(f"Duplicate entry in payload for {name}")

        if frappe.db.exists("Invoice Charge", name):
            frappe.throw(f"Invoice Charge {name} already exists")

        processed_names.add(name)

        validated.append(
            {
                "name": name,
                "invoice": invoice_name,
                "charge_type": charge_type,
                "amount": amount,
            }
        )

    for item in validated:
        doc = frappe.get_doc(
            {
                "doctype": "Invoice Charge",
                **item,
            }
        )
        doc.insert(set_name=item["name"])
        results.append(_format_doc(doc))

    return results


@frappe.whitelist(methods=["POST"])
def create_invoice_charge():
    try:
        data = _get_request_data()
        payload = data if isinstance(data, list) else [data]

        grouped = {}

        for item in payload:
            invoice = str(item.get("invoice", "")).strip()
            charge_type = str(item.get("charge_type", "")).strip()
            amount = item.get("amount")

            if not invoice or not charge_type or amount is None:
                return send_response(
                    "error",
                    "invoice, charge_type and amount are required",
                    status_code=400,
                )

            if not frappe.db.exists("Sales Invoice", invoice):
                return send_response(
                    "error", f"Invalid invoice {invoice}", status_code=400
                )

            grouped.setdefault(invoice, []).append(
                {
                    "charge_type": charge_type,
                    "amount": amount,
                }
            )

        results = []

        for invoice, charges in grouped.items():
            docs = process_and_insert_charges(invoice, charges)
            results.extend(docs)

        frappe.db.commit()

        return send_response(
            "success",
            "Invoice charges created successfully",
            data=results,
            status_code=201,
        )

    except frappe.DuplicateEntryError as de:
        frappe.db.rollback()
        return send_response("error", message=str(de), status_code=409)

    except frappe.exceptions.ValidationError as ve:
        frappe.db.rollback()
        return send_response("error", message=str(ve), status_code=400)

    except Exception as e:
        frappe.db.rollback()
        error_traceback = frappe.get_traceback()
        frappe.log_error(title="Invoice Charge API Error", message=error_traceback)

        return send_response(
            "error",
            message=str(e),
            data={"traceback": error_traceback},
            status_code=500,
        )


@frappe.whitelist(methods=["PUT", "PATCH"])
def update_invoice_charge(id=None):
    try:
        data = _get_request_data()
        raw_id = id if id is not None else data.get("id")
        record_id = str(raw_id).strip() if raw_id is not None else ""

        if not record_id:
            return send_response("error", "ID required", status_code=400)

        if not frappe.db.exists("Invoice Charge", record_id):
            return send_response("error", "Record not found", status_code=404)

        doc = frappe.get_doc("Invoice Charge", record_id)

        if "charge_type" in data:
            doc.charge_type = str(data.get("charge_type")).strip()

        if "amount" in data:
            try:
                doc.amount = float(data.get("amount"))
            except ValueError:
                return send_response(
                    "error", "Amount must be a valid number", status_code=400
                )

        doc.save()
        frappe.db.commit()

        return send_response(
            "success",
            "Updated successfully",
            data=_format_doc(doc),
        )

    except Exception as e:
        frappe.db.rollback()
        return send_response("error", str(e), status_code=500)


@frappe.whitelist(methods=["DELETE"])
def delete_invoice_charge(id):
    try:
        record_id = str(id).strip() if id is not None else ""

        if not record_id:
            return send_response("error", "ID required", status_code=400)

        if not frappe.db.exists("Invoice Charge", record_id):
            return send_response("error", "Record not found", status_code=404)

        frappe.delete_doc("Invoice Charge", record_id)
        frappe.db.commit()

        return send_response(
            "success",
            "Deleted successfully",
            data={"id": record_id},
        )

    except Exception as e:
        frappe.db.rollback()
        return send_response("error", str(e), status_code=500)
