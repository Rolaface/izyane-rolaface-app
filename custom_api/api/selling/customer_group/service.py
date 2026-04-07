import math
import frappe
from .utils import build_tree


def get_customer_groups(params):
    search_term = (params.get("search") or "").strip().lower()
    parent_customer_group = params.get("parent_customer_group")
    is_group = params.get("is_group")
    as_tree = int(params.get("as_tree", 1))

    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 100))
    start = (page - 1) * page_size

    filters = {}
    if parent_customer_group:
        filters["parent_customer_group"] = parent_customer_group
    if is_group is not None:
        filters["is_group"] = int(is_group)

    or_filters = []
    if search_term:
        or_filters = [
            ["name", "like", f"%{search_term}%"],
            ["customer_group_name", "like", f"%{search_term}%"],
        ]

    total_items = frappe.db.count("Customer Group", filters=filters)

    customer_groups = frappe.get_all(
        "Customer Group",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name",
            "customer_group_name",
            "parent_customer_group",
            "is_group",
            "default_price_list",
            "payment_terms",
            "creation",
            "modified"
        ],
        order_by="modified desc, name desc",
        limit_start=start,
        limit_page_length=page_size,
    )

    restriction_docs = frappe.get_all(
        "Custom Customer Group Item Restriction",
        fields=["name", "customer_group", "restriction_mode", "enabled"]
    )

    restriction_map = {r["customer_group"]: r for r in restriction_docs}

    restriction_items = frappe.get_all(
        "Custom Item Restriction",
        fields=["parent", "target_type", "item", "item_group"]
    )

    items_map = {}
    for item in restriction_items:
        items_map.setdefault(item["parent"], []).append({
            "target_type": item["target_type"],
            "item": item["item"],
            "item_group": item["item_group"]
        })

    rows = []

    for doc in customer_groups:
        restriction = None

        if doc["name"] in restriction_map:
            res = restriction_map[doc["name"]]

            restriction = {
                "id": res["name"],
                "restriction_mode": res["restriction_mode"],
                "enabled": res["enabled"],
                "items": items_map.get(res["name"], [])
            }

        rows.append({
            "id": doc["name"],
            "customer_group_name": doc["customer_group_name"],
            "parent_customer_group": doc["parent_customer_group"],
            "is_group": doc["is_group"],
            "default_price_list": doc["default_price_list"],
            "payment_terms": doc["payment_terms"],
            "timestamps": {
                "created_at": doc["creation"],
                "modified_at": doc["modified"]
            },
            "restrictions": restriction
        })

    if as_tree:
        rows = build_tree(rows)

    total_pages = math.ceil(total_items / page_size) if page_size else 1

    return {
        "data": rows,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "items_in_page": len(rows),
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }


def get_customer_group_by_id(record_id):
    doc = frappe.get_doc("Customer Group", record_id)

    restriction_name = frappe.db.get_value(
        "Custom Customer Group Item Restriction",
        {"customer_group": doc.name},
        "name"
    )

    restriction = None

    if restriction_name:
        res_doc = frappe.get_doc(
            "Custom Customer Group Item Restriction",
            restriction_name
        )

        restriction = {
            "id": res_doc.name,
            "restriction_mode": res_doc.restriction_mode,
            "enabled": res_doc.enabled,
            "items": [
                {
                    "target_type": item.target_type,
                    "item": item.item,
                    "item_group": item.item_group
                }
                for item in res_doc.get("items", [])
            ]
        }

    return {
        "id": doc.name,
        "customer_group_name": doc.customer_group_name,
        "parent_customer_group": doc.parent_customer_group,
        "is_group": doc.is_group,
        "default_price_list": doc.default_price_list,
        "payment_terms": doc.payment_terms,
        "timestamps": {
            "created_at": doc.creation,
            "modified_at": doc.modified
        },
        "restrictions": restriction
    }


def create_customer_group(data):
    doc = frappe.get_doc({
        "doctype": "Customer Group",
        "customer_group_name": data.get("customer_group_name"),
        "parent_customer_group": data.get("parent_customer_group")
        or data.get("parent")
        or "All Customer Groups",
        "is_group": int(data.get("is_group", 0)),
        "default_price_list": data.get("default_price_list"),
        "payment_terms": data.get("payment_terms"),
    })

    doc.insert(ignore_permissions=False)

    if data.get("restrictions"):
        rest_data = data.get("restrictions")

        rest_doc = frappe.get_doc({
            "doctype": "Custom Customer Group Item Restriction",
            "customer_group": doc.name,
            "restriction_mode": rest_data.get("restriction_mode", "Allow"),
            "enabled": int(rest_data.get("enabled", 1)),
        })

        for item in rest_data.get("items", []):
            rest_doc.append("items", {
                "target_type": item.get("target_type"),
                "item": item.get("item"),
                "item_group": item.get("item_group")
            })

        rest_doc.insert(ignore_permissions=False)

    frappe.db.commit()

    return get_customer_group_by_id(doc.name)


def update_customer_group(record_name, data):
    doc = frappe.get_doc("Customer Group", record_name)

    fields = [
        "customer_group_name",
        "parent_customer_group",
        "is_group",
        "default_price_list",
        "payment_terms"
    ]

    for field in fields:
        if field in data:
            doc.set(field, data.get(field))

    doc.save(ignore_permissions=False)

    if "restrictions" in data:
        rest_data = data.get("restrictions")

        restriction_name = frappe.db.get_value(
            "Custom Customer Group Item Restriction",
            {"customer_group": doc.name},
            "name"
        )

        if not rest_data and restriction_name:
            frappe.delete_doc(
                "Custom Customer Group Item Restriction",
                restriction_name,
                ignore_permissions=False
            )

        elif rest_data:
            if restriction_name:
                rest_doc = frappe.get_doc(
                    "Custom Customer Group Item Restriction",
                    restriction_name
                )

                if "restriction_mode" in rest_data:
                    rest_doc.restriction_mode = rest_data.get("restriction_mode")

                if "enabled" in rest_data:
                    rest_doc.enabled = int(rest_data.get("enabled"))

                if "items" in rest_data:
                    rest_doc.set("items", [])
                    for item in rest_data.get("items", []):
                        rest_doc.append("items", {
                            "target_type": item.get("target_type"),
                            "item": item.get("item"),
                            "item_group": item.get("item_group")
                        })

                rest_doc.save(ignore_permissions=False)

            else:
                rest_doc = frappe.get_doc({
                    "doctype": "Custom Customer Group Item Restriction",
                    "customer_group": doc.name,
                    "restriction_mode": rest_data.get("restriction_mode", "Allow"),
                    "enabled": int(rest_data.get("enabled", 1)),
                })

                for item in rest_data.get("items", []):
                    rest_doc.append("items", {
                        "target_type": item.get("target_type"),
                        "item": item.get("item"),
                        "item_group": item.get("item_group")
                    })

                rest_doc.insert(ignore_permissions=False)

    frappe.db.commit()
    doc.reload()

    return get_customer_group_by_id(doc.name)


def delete_customer_group(record_id):
    restriction_name = frappe.db.get_value(
        "Custom Customer Group Item Restriction",
        {"customer_group": record_id},
        "name"
    )

    if restriction_name:
        frappe.delete_doc(
            "Custom Customer Group Item Restriction",
            restriction_name,
            ignore_permissions=False
        )

    frappe.delete_doc("Customer Group", record_id, ignore_permissions=False)
    frappe.db.commit()

    return {"id": record_id}