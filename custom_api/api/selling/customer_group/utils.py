import frappe


def get_arg(key, default=None):
    return frappe.request.args.get(key, default)


def get_request_data():
    try:
        if hasattr(frappe, "request") and frappe.request and getattr(frappe.request, "data", None):
            data_str = frappe.request.data.decode("utf-8")
            parsed_data = frappe.parse_json(data_str)
            if isinstance(parsed_data, dict):
                return parsed_data
    except Exception:
        pass
    return frappe.local.form_dict or {}

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