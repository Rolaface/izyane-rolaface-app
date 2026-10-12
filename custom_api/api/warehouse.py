import frappe
from custom_api.helper import get_warehouses
from custom_api.utils.response import send_response

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_all_warehouse():
    company = frappe.defaults.get_user_default("Company")
    disabled = frappe.request.args.get("is_disabled", None)

    ware_house = get_warehouses(company, disabled)
    return send_response(
        status="success",
        message="Warehouse fetched successfully.",
        data={
            "ware_house": ware_house
        },
        status_code=200,
        http_status=200,
    )


def _get_arg(key, default=None):
    return frappe.request.args.get(key, default)


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_warehouse_tree():
    try:
        is_group = _get_arg("is_group")
        parent_warehouse = _get_arg("parent_warehouse")

        filters = {}
        if is_group is not None:
            filters["is_group"] = int(is_group)
        if parent_warehouse:
            filters["parent_warehouse"] = parent_warehouse

        warehouses = frappe.get_all(
            "Warehouse",
            filters=filters,
            fields=[
                "name",
                "warehouse_name",
                "parent_warehouse",
                "is_group",
                "lft",
                "rgt",
                "company",
                "custom_warehouse_code"
            ],
            order_by="lft asc"
        )

        if not warehouses:
            return send_response(
                status="success",
                message="No Warehouses found.",
                data={
                    "total": 0,
                    "warehouses": []
                },
                status_code=200,
                http_status=200
            )

        bin_counts_raw = frappe.db.sql("""
            SELECT warehouse, COUNT(name) as bin_count
            FROM `tabBin`
            GROUP BY warehouse
        """, as_dict=True)

        count_map = {row.warehouse: row.bin_count for row in bin_counts_raw}

        for wh in warehouses:
            wh["bin_count"] = count_map.get(wh["name"], 0)

        def build_tree(nodes, parent=None):
            tree = []
            for node in nodes:
                current_parent = node.get("parent_warehouse") or None
                target_parent = parent or None

                if current_parent == target_parent:
                    node["children"] = build_tree(nodes, parent=node["name"])
                    tree.append(node)
            return tree

        starting_parent = parent_warehouse or None
        tree = build_tree(warehouses, parent=starting_parent)

        return send_response(
            status="success",
            message="Warehouse tree fetched successfully.",
            data={
                "total": len(warehouses),
                "warehouses": tree
            },
            status_code=200,
            http_status=200
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Warehouse Tree API Error")
        return send_response(
            status="error",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500
        )