import math
import frappe
from custom_api.utils.response import send_response, send_response_list


def _get_arg(key, default=None):
    return frappe.request.args.get(key, default)

def _get_request_data():
    try:
        if hasattr(frappe, "request") and frappe.request and getattr(frappe.request, "data", None):
            data_str = frappe.request.data.decode("utf-8")
            parsed_data = frappe.parse_json(data_str)
            if isinstance(parsed_data, dict):
                return parsed_data
    except Exception:
        pass
    return frappe.local.form_dict or {}

def _format_customer_group_doc(doc):
    base_data = {
        "id": doc.name,
        "customer_group_name": doc.customer_group_name,
        "parent_customer_group": doc.parent_customer_group,
        "is_group": doc.is_group,
        "default_price_list": doc.default_price_list,
        "payment_terms": doc.payment_terms,
        "timestamps": {"created_at": doc.creation, "modified_at": doc.modified},
        "restrictions": None
    }

    # Fetch associated custom restrictions if they exist
    restriction_name = frappe.db.get_value("Custom Customer Group Item Restriction", {"customer_group": doc.name}, "name")
    if restriction_name:
        res_doc = frappe.get_doc("Custom Customer Group Item Restriction", restriction_name)
        base_data["restrictions"] = {
            "id": res_doc.name,
            "restriction_mode": res_doc.restriction_mode,
            "enabled": res_doc.enabled,
            "items": [
                {
                    "target_type": item.target_type,
                    "item": item.item,
                    "item_group": item.item_group
                } for item in res_doc.get("items", [])
            ]
        }
        
    return base_data

def build_tree(flat_list):
    tree = []
    lookup = {}

    for item in flat_list:
        item["children"] = []
        lookup[item["id"]] = item

    for item in flat_list:
        parent_id = item.get("parent_customer_group")
        if parent_id and parent_id in lookup:
            lookup[parent_id]["children"].append(item)
        else:
            tree.append(item)

    return tree

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customer_groups():
    search_term = _get_arg("search", "").strip().lower()
    parent_customer_group = _get_arg("parent_customer_group")
    is_group = _get_arg("is_group")
    as_tree = int(_get_arg("as_tree", 1))

    page = int(_get_arg("page", 1))
    page_size = int(_get_arg("page_size", 100))
    start = (page - 1) * page_size

    filters = {}
    if parent_customer_group: filters["parent_customer_group"] = parent_customer_group
    if is_group is not None: filters["is_group"] = int(is_group)

    or_filters = []
    if search_term:
        or_filters = [
            ["name", "like", f"%{search_term}%"],
            ["customer_group_name", "like", f"%{search_term}%"],
        ]

    count_result = frappe.get_all(
        "Customer Group",
        filters=filters,
        or_filters=or_filters,
        fields=["count(name) as total_count"],
    )
    total_items = count_result[0].get("total_count", 0) if count_result else 0

    raw_data = frappe.get_all(
        "Customer Group",
        filters=filters,
        or_filters=or_filters,
        fields=["name"],
        order_by="modified desc, name desc",
        limit_start=start,
        limit_page_length=page_size,
    )

    rows = []
    for row in raw_data:
        doc = frappe.get_doc("Customer Group", row.name)
        rows.append(_format_customer_group_doc(doc))

    if as_tree:
        rows = build_tree(rows)

    total_pages = math.ceil(total_items / page_size) if page_size else 1

    return send_response_list(
        status="success",
        message="Customer Groups fetched successfully.",
        data={
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
        },
        status_code=200,
        http_status=200,
    )

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customer_group(id):
    if not id:
        return send_response(status="error", message="Record ID (id) is required.", status_code=400, http_status=400)

    try:
        doc = frappe.get_doc("Customer Group", id)
        return send_response(
            status="success",
            message="Record fetched successfully.",
            data=_format_customer_group_doc(doc),
            status_code=200,
            http_status=200,
        )
    except frappe.DoesNotExistError:
        return send_response(status="error", message=f"Customer Group '{id}' not found.", status_code=404, http_status=404)
    except Exception as e:
        return send_response(status="error", message=str(e), status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_customer_group():
    data = _get_request_data()
    required_fields = ["customer_group_name"]
    
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return send_response(status="error", message=f"Missing required fields: {', '.join(missing)}", status_code=400, http_status=400)

    try:
        # 1. Create standard Customer Group (Will run whether restrictions exist or not)
        doc = frappe.get_doc({
            "doctype": "Customer Group",
            "customer_group_name": data.get("customer_group_name"),
            "parent_customer_group": data.get("parent_customer_group") or data.get("parent") or "All Customer Groups",
            "is_group": int(data.get("is_group", 0)),
            "default_price_list": data.get("default_price_list"),
            "payment_terms": data.get("payment_terms"),
        })

        doc.insert(ignore_permissions=False)

        # 2. Check for Restrictions Payload and create custom doctype ONLY if provided
        if "restrictions" in data and data.get("restrictions"):
            rest_data = data.get("restrictions", {})
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
        
        return send_response(
            status="success",
            message="Customer Group created successfully.",
            data=_format_customer_group_doc(doc),
            status_code=201, 
            http_status=201,
        )
    except frappe.UniqueValidationError:
        frappe.db.rollback()
        return send_response(status="error", message="A Customer Group with this name already exists.", status_code=409, http_status=409)
    except Exception as e:
        frappe.db.rollback()
        return send_response(status="error", message=str(e), status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["POST", "PUT", "PATCH"])
def update_customer_group(id=None, **kwargs):
    data = _get_request_data()
    record_name = id or data.get("id") or _get_arg("id")

    if not record_name:
        return send_response(status="error", message="Record ID (id) is required.", status_code=400, http_status=400)

    try:
        # 1. Update the base Customer Group doc
        doc = frappe.get_doc("Customer Group", record_name)
        updatable_fields = ["customer_group_name", "parent_customer_group", "is_group", "default_price_list", "payment_terms"]
        
        for field in updatable_fields:
            if field in data:
                doc.set(field, data.get(field))

        doc.save(ignore_permissions=False)

        # 2. Update, Create, or Delete Restriction doc
        if "restrictions" in data:
            rest_data = data.get("restrictions")
            restriction_name = frappe.db.get_value("Custom Customer Group Item Restriction", {"customer_group": doc.name}, "name")
            
            # If payload explicitly passes null/empty for restrictions, and one exists, delete it
            if not rest_data and restriction_name:
                frappe.delete_doc("Custom Customer Group Item Restriction", restriction_name, ignore_permissions=False)
            
            # If payload has restriction data
            elif rest_data:
                if restriction_name:
                    # Update existing restriction
                    rest_doc = frappe.get_doc("Custom Customer Group Item Restriction", restriction_name)
                    if "restriction_mode" in rest_data:
                        rest_doc.restriction_mode = rest_data.get("restriction_mode")
                    if "enabled" in rest_data:
                        rest_doc.enabled = int(rest_data.get("enabled"))
                    
                    if "items" in rest_data:
                        rest_doc.set("items", []) # Clear old items
                        for item in rest_data.get("items", []):
                            rest_doc.append("items", {
                                "target_type": item.get("target_type"),
                                "item": item.get("item"),
                                "item_group": item.get("item_group")
                            })
                    rest_doc.save(ignore_permissions=False)
                else:
                    # Create new restriction because it didn't exist previously (User added it during update)
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
        
        return send_response(
            status="success",
            message="Customer Group updated successfully.",
            data=_format_customer_group_doc(doc),
            status_code=200,
            http_status=200,
        )
    except frappe.DoesNotExistError:
        return send_response(status="error", message=f"Customer Group '{record_name}' not found.", status_code=404, http_status=404)
    except Exception as e:
        frappe.db.rollback()
        return send_response(status="error", message=str(e), status_code=500, http_status=500)

@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_customer_group(id):
    if not id:
        return send_response(status="error", message="Record ID (id) is required.", status_code=400, http_status=400)

    try:
        # Check and Delete Custom Restriction Doc First
        restriction_name = frappe.db.get_value("Custom Customer Group Item Restriction", {"customer_group": id}, "name")
        if restriction_name:
            frappe.delete_doc("Custom Customer Group Item Restriction", restriction_name, ignore_permissions=False)

        frappe.delete_doc("Customer Group", id, ignore_permissions=False)
        frappe.db.commit()

        return send_response(
            status="success",
            message=f"Customer Group '{id}' deleted successfully.",
            data={"id": id},
            status_code=200,
            http_status=200,
        )
    except frappe.DoesNotExistError:
        frappe.db.rollback()
        return send_response(status="error", message=f"Customer Group '{id}' not found.", status_code=404, http_status=404)
    except Exception as e:
        frappe.db.rollback()
        return send_response(status="error", message=str(e), status_code=500, http_status=500)