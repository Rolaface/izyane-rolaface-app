from typing import Any

import frappe
from frappe.utils import flt
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

from .constant import ALLOWED_FIELDS, LIST_FIELDS, SORT_FIELDS
from .utils import (
    build_filters,
    ensure_return_document,
    get_item_reference,
    get_source_invoice,
    normalize_payload,
    validate_dates,
    validate_payload,
)


def get_source_rows(source_name: str) -> dict:
    rows = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": source_name, "parenttype": "Sales Invoice"},
        fields=["name", "item_code", "qty"],
        order_by="idx asc",
    )
    return {row.name: flt(row.qty) for row in rows}


def get_adjusted_qty(source_name: str, source_row: str) -> float:
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(ABS(child.qty)), 0)
        FROM `tabSales Invoice Item` child
        INNER JOIN `tabSales Invoice` parent ON parent.name = child.parent
        WHERE parent.return_against = %s
          AND parent.docstatus = 1
          AND (parent.is_return = 1 OR parent.is_debit_note = 1)
          AND child.sales_invoice_item = %s
        """,
        (source_name, source_row),
    )
    return flt(result[0][0]) if result else 0


def resolve_items(document: Any, payload_items: list[dict]) -> list:
    by_name = {
        row.sales_invoice_item: row
        for row in document.items
        if row.get("sales_invoice_item")
    }
    by_code = {}
    for row in document.items:
        by_code.setdefault(row.item_code, []).append(row)

    source_rows = get_source_rows(document.return_against)
    selected = []
    used = set()
    for index, payload_item in enumerate(payload_items, 1):
        reference = get_item_reference(payload_item)
        row = by_name.get(reference) if reference else None
        if row is None:
            matches = by_code.get(payload_item.get("item_code"), [])
            if len(matches) != 1:
                message = (
                    "item_code is ambiguous; provide sales_invoice_item."
                    if matches
                    else "item does not exist in the source invoice."
                )
                raise frappe.ValidationError(f"Row {index}: {message}")
            row = matches[0]

        if row.name in used:
            raise frappe.ValidationError(f"Row {index}: duplicate invoice item.")
        used.add(row.name)

        source_qty = source_rows.get(row.sales_invoice_item, 0)
        available_qty = source_qty - get_adjusted_qty(
            document.return_against, row.sales_invoice_item
        )
        quantity = flt(payload_item.get("qty"))
        if quantity > available_qty + 1e-9:
            item_desc = f"Row {index} ({payload_item.get('item_code') or row.item_code})"
            if available_qty <= 0:
                raise frappe.ValidationError(
                    f"{item_desc}: This item has already been fully adjusted/returned against invoice {document.return_against}. Remaining returnable quantity is 0."
                )
            else:
                raise frappe.ValidationError(
                    f"{item_desc}: Entered quantity ({quantity:g}) exceeds the remaining returnable quantity ({max(available_qty, 0):g}) for invoice {document.return_against}."
                )

        serial_no = payload_item.get("serial_no")
        if isinstance(serial_no, list):
            serial_no = "\n".join(str(value) for value in serial_no)
        if serial_no is not None and not isinstance(serial_no, str):
            raise frappe.ValidationError(f"Row {index}: serial_no must be a string or array.")
        if serial_no is not None:
            row.serial_no = serial_no
        if row.get("has_serial_no") and row.serial_no:
            serial_count = len([value for value in row.serial_no.splitlines() if value.strip()])
            if quantity != int(quantity) or serial_count != int(quantity):
                raise frappe.ValidationError(f"Row {index}: serial count must match qty.")

        row.qty = -abs(quantity) if document.is_return else abs(quantity)
        if payload_item.get("rate") is not None:
            rate_val = flt(payload_item.get("rate"))
            row.rate = rate_val
            row.price_list_rate = rate_val
        selected.append(row)

    if not selected:
        raise frappe.ValidationError("At least one item is required.")
    return selected


def set_default_debit_items(document: Any) -> None:
    source_rows = get_source_rows(document.return_against)
    items = []
    for row in document.items:
        available_qty = source_rows.get(row.sales_invoice_item, 0) - get_adjusted_qty(
            document.return_against, row.sales_invoice_item
        )
        if available_qty > 0:
            row.qty = available_qty
            items.append(row)
    if not items:
        raise frappe.ValidationError(
            f"All items for invoice '{document.return_against}' have already been fully returned or adjusted. No returnable quantity remains."
        )
    document.set("items", items)


def apply_fields(document: Any, data: dict) -> None:
    for fieldname in ALLOWED_FIELDS:
        if data.get(fieldname) is not None:
            document.set(fieldname, data[fieldname])

    if data.get("reason") is not None or data.get("payment_mode") is not None:
        if not document.custom_details:
            document.append(
                "custom_details",
                {"reason": data.get("reason"), "payment_mode": data.get("payment_mode")},
            )
        else:
            detail = document.custom_details[0]
            if data.get("reason") is not None:
                detail.reason = data["reason"]
            if data.get("payment_mode") is not None:
                detail.payment_mode = data["payment_mode"]


def create_sales_return(data: dict):
    data = normalize_payload(data)
    validate_payload(data)
    source = get_source_invoice(data["return_against"])
    validate_dates(data, source)

    document = make_sales_return(source.name)
    document.is_return = 1 if data.get("doc_type", "Credit Note") == "Credit Note" else 0
    document.is_debit_note = 0 if document.is_return else 1
    if document.is_debit_note:
        document.update_stock = 0

    meta = frappe.get_meta("Sales Invoice")
    series_list = [s.strip() for s in (meta.get_field("naming_series").options or "").split("\n") if s.strip()]
    if document.is_return and len(series_list) > 1:
        document.naming_series = series_list[1]
    elif document.is_debit_note and len(series_list) > 2:
        document.naming_series = series_list[2]

    apply_fields(document, data)
    if data.get("items") is not None:
        document.set("items", resolve_items(document, data["items"]))
    elif document.is_debit_note:
        set_default_debit_items(document)
    else:
        document.set("items", [row for row in document.items if flt(row.qty) < 0])

    if not document.items:
        raise frappe.ValidationError(
            f"All items for invoice '{document.return_against}' have already been fully returned or adjusted. No returnable quantity remains."
        )
    document.update_outstanding_for_self = 0
    document.calculate_taxes_and_totals()
    document.insert()
    return document


def update_sales_return(invoice_id: str, data: dict):
    data = normalize_payload(data)
    validate_payload(data, is_update=True)
    invoice = ensure_return_document(frappe.get_doc("Sales Invoice", invoice_id))
    if not frappe.has_permission("Sales Invoice", "write", invoice):
        raise frappe.PermissionError("You do not have permission to edit this sales return.")
    if invoice.docstatus != 0:
        raise frappe.ValidationError("Only draft sales returns can be edited.")

    source = get_source_invoice(invoice.return_against)
    validate_dates(data, source)
    expected_type = "Credit Note" if invoice.is_return else "Debit Note"
    if data.get("doc_type") and data["doc_type"] != expected_type:
        raise frappe.ValidationError("doc_type cannot be changed after creation.")

    apply_fields(invoice, data)
    if data.get("items") is not None:
        invoice.set("items", resolve_items(invoice, data["items"]))
    invoice.calculate_taxes_and_totals()
    invoice.save()
    return invoice


def get_sales_returns(args: dict, page: int, page_size: int, sort_by: str = "creation", sort_order: str = "desc"):
    if page < 1 or page_size < 1 or page_size > 500:
        raise frappe.ValidationError("page must be positive and page_size must be between 1 and 500.")
    if sort_by not in SORT_FIELDS:
        raise frappe.ValidationError(f"Invalid sort_by field: {sort_by}")
    sort_order = str(sort_order).lower()
    if sort_order not in {"asc", "desc"}:
        raise frappe.ValidationError("sort_order must be asc or desc.")

    filters = build_filters(args)
    search = str(args.get("search") or "").strip()
    or_filters = [[field, "like", f"%{search}%"] for field in ("name", "customer_name", "return_against")] if search else None
    order_by = f"`tabSales Invoice`.`{sort_by}` {sort_order}"
    rows = frappe.get_list(
        "Sales Invoice",
        filters=filters,
        or_filters=or_filters,
        fields=LIST_FIELDS,
        limit_start=(page - 1) * page_size,
        limit_page_length=page_size,
        order_by=order_by,
    )
    total = len(frappe.get_list("Sales Invoice", filters=filters, or_filters=or_filters, fields=["name"], limit_page_length=0))
    for row in rows:
        row["id"] = row.pop("name")
        row["doc_type"] = "Credit Note" if row.pop("is_return") else "Debit Note"
    return rows, total, (total + page_size - 1) // page_size


def delete_sales_return(invoice_id: str) -> None:
    invoice = ensure_return_document(frappe.get_doc("Sales Invoice", invoice_id))
    if not frappe.has_permission("Sales Invoice", "delete", invoice):
        raise frappe.PermissionError("You do not have permission to delete this sales return.")
    if invoice.docstatus != 0:
        raise frappe.ValidationError("Only draft sales returns can be deleted.")
    frappe.delete_doc("Sales Invoice", invoice.name)
