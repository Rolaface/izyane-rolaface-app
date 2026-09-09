import json
from typing import Any

import frappe
from frappe.utils import flt, getdate

from .constant import DOC_TYPES


def normalize_payload(data: Any) -> dict:
    if not isinstance(data, dict):
        raise frappe.ValidationError("Request body must be a JSON object.")
    payload = dict(data)
    if isinstance(payload.get("items"), str):
        try:
            payload["items"] = json.loads(payload["items"])
        except json.JSONDecodeError as exc:
            raise frappe.ValidationError("items must be a valid JSON array.") from exc
    return payload


def validate_payload(data: dict, is_update: bool = False) -> None:
    if not is_update:
        if not data.get("return_against"):
            raise frappe.ValidationError("return_against is required.")
        if data.get("doc_type", "Credit Note") not in DOC_TYPES:
            raise frappe.ValidationError("doc_type must be Credit Note or Debit Note.")

    items = data.get("items")
    if items is None:
        return
    if not isinstance(items, list) or not items:
        raise frappe.ValidationError("items must be a non-empty array.")

    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise frappe.ValidationError(f"Row {index}: item must be an object.")
        if not item.get("item_code") and not item.get("sales_invoice_item"):
            raise frappe.ValidationError(f"Row {index}: item_code or sales_invoice_item is required.")
        if item.get("qty") is None:
            raise frappe.ValidationError(f"Row {index}: qty is required.")
        try:
            quantity = flt(item.get("qty"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise frappe.ValidationError(f"Row {index}: qty must be a positive number.") from exc
        if quantity <= 0:
            raise frappe.ValidationError(f"Row {index}: qty must be greater than zero.")


def get_source_invoice(name: str):
    if not name:
        raise frappe.ValidationError("return_against is required.")
    if not frappe.db.exists("Sales Invoice", name):
        raise frappe.DoesNotExistError(f"Sales Invoice '{name}' does not exist.")
    source = frappe.get_cached_doc("Sales Invoice", name)
    if source.docstatus != 1:
        raise frappe.ValidationError("Returns can only be created against submitted invoices.")
    if source.is_return or source.is_debit_note:
        raise frappe.ValidationError("The source invoice cannot be a return or debit note.")
    return source


def ensure_return_document(invoice):
    if not invoice.is_return and not invoice.is_debit_note:
        raise frappe.ValidationError("The document is not a Credit Note or Sales Debit Note.")
    if not invoice.return_against:
        raise frappe.ValidationError("The sales return has no source invoice.")
    return invoice


def validate_dates(data: dict, source) -> None:
    posting_date = data.get("posting_date")
    due_date = data.get("due_date")
    if posting_date and getdate(posting_date) < getdate(source.posting_date):
        raise frappe.ValidationError("posting_date cannot be before the source invoice date.")
    if posting_date and due_date and getdate(due_date) < getdate(posting_date):
        raise frappe.ValidationError("due_date cannot be before posting_date.")


def get_item_reference(item: dict):
    return item.get("sales_invoice_item") or item.get("item_row_id")


def build_filters(args: dict) -> dict:
    filters = {"return_against": ["is", "set"]}
    doc_type = args.get("doc_type")
    if doc_type == "Credit Note":
        filters.update({"is_return": 1, "is_debit_note": 0})
    elif doc_type == "Debit Note":
        filters.update({"is_return": 0, "is_debit_note": 1})
    elif doc_type:
        raise frappe.ValidationError("doc_type must be Credit Note or Debit Note.")
    else:
        filters.update({"is_return": ["in", [0, 1]], "is_debit_note": ["in", [0, 1]]})

    for fieldname in ("customer", "return_against"):
        if args.get(fieldname):
            filters[fieldname] = args[fieldname]

    if args.get("status"):
        status = args["status"]
        if isinstance(status, str) and status.startswith("["):
            try:
                status = json.loads(status)
            except json.JSONDecodeError as exc:
                raise frappe.ValidationError("status must be a valid JSON array.") from exc
        filters["status"] = ["in", status] if isinstance(status, list) else status

    from_date, to_date = args.get("from_date"), args.get("to_date")
    if from_date or to_date:
        if not from_date or not to_date:
            raise frappe.ValidationError("from_date and to_date are both required.")
        if getdate(from_date) > getdate(to_date):
            raise frappe.ValidationError("from_date cannot be after to_date.")
        filters["posting_date"] = ["between", [from_date, to_date]]
    return filters
