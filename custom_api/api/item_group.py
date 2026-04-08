import frappe
from custom_api.utils.response import send_response

def _get_arg(key, default=None):
    return frappe.request.args.get(key, default)

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_item_group_tree():
    try:
        is_group = _get_arg("is_group")
        parent_item_group = _get_arg("parent_item_group")

        filters = {}
        if is_group is not None:
            filters["is_group"] = int(is_group)
        if parent_item_group:
            filters["parent_item_group"] = parent_item_group
        item_groups = frappe.get_all(
            "Item Group",
            filters=filters,
            fields=[
                "name",
                "item_group_name",
                "parent_item_group",
                "is_group",
                "lft",
                "rgt"
            ],
            order_by="lft asc"
        )

        if not item_groups:
            return send_response(
                status="success",
                message="No Item Groups found.",
                data={
                    "total": 0,
                    "item_groups": []
                },
                status_code=200,
                http_status=200
            )
        item_counts_raw = frappe.db.sql("""
            SELECT item_group, COUNT(name) as item_count 
            FROM `tabItem` 
            GROUP BY item_group
        """, as_dict=True)
        
        count_map = {row.item_group: row.item_count for row in item_counts_raw}
        for group in item_groups:
            group["item_count"] = count_map.get(group["name"], 0)

        def build_tree(groups, parent=None):
            tree = []
            for group in groups:
                current_parent = group.get("parent_item_group") or None
                target_parent = parent or None

                if current_parent == target_parent:
                    group["children"] = build_tree(groups, parent=group["name"])
                    tree.append(group)
            return tree

        starting_parent = parent_item_group or None
        tree = build_tree(item_groups, parent=starting_parent)

        return send_response(
            status="success",
            message="Item Group tree fetched successfully.",
            data={
                "total": len(item_groups),
                "item_groups": tree
            },
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Item Group Tree API Error")
        return send_response(
            status="error",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )