import frappe
from frappe.utils import cint
from .utils import (
    CLASS_CODE_SEGMENT_LENGTH,
	ancestor_codes_for,
	build_classification_filters,
	clamp_page_size,
	decode_cursor,
	encode_cursor,
	normalize_class_code,
)


CLASSIFICATION_DOCTYPE = "Custom Item Classification"
CLASSIFICATION_FIELDS = ["name as id", "class_code", "class_name", "class_level", "is_active"]


def create_classification(data: dict):
    doc = frappe.new_doc("Custom Item Classification")
    doc.update({
        "class_code": data.get("class_code"),
        "class_name": data.get("class_name"),
        "class_level": cint(data.get("class_level") or 0),
        "is_active": 1 if data.get("is_active") in [1, True, "1", "true"] else 0,
    })

    doc.insert(ignore_permissions=True)
    return doc


def update_classification(classification_id: str, data: dict):
    doc = frappe.get_doc("Custom Item Classification", classification_id)

    field_map = {
        "class_code": "class_code",
        "class_name": "class_name",
        "class_level": "class_level",
    }

    for k, v in field_map.items():
        if data.get(k) is not None:
            if k == "class_level":
                setattr(doc, v, cint(data.get(k)))
            else:
                setattr(doc, v, data.get(k))

    if data.get("is_active") is not None:
        doc.is_active = 1 if data.get("is_active") in [1, True, "1", "true"] else 0

    doc.save(ignore_permissions=True)
    return doc


def get_classification_by_id(classification_id: str) -> dict:
    doc = frappe.get_doc("Custom Item Classification", classification_id)
    
    return {
        "id": doc.name,
        "class_code": doc.class_code,
        "class_name": doc.class_name,
        "class_level": doc.class_level,
        "is_active": bool(doc.is_active),
        "creation": doc.creation,
        "modified": doc.modified,
    }

def get_classification_by_code(class_code: str) -> dict | None:
    class_code = normalize_class_code(class_code)
    doc_name = frappe.db.get_value(
        CLASSIFICATION_DOCTYPE,
        {"class_code": class_code},
        "name"
    )

    if not doc_name:
        return None

    return get_classification_by_id(doc_name)


def _serialize_classification(item: dict, has_children: bool | None = None) -> dict:
	result = {
		"id": item.get("id") or item.get("name"),
		"class_code": item.get("class_code"),
		"class_name": item.get("class_name"),
		"class_level": cint(item.get("class_level")),
		"is_active": bool(item.get("is_active")),
	}
	if has_children is not None:
		result["has_children"] = has_children
	return result


def _has_children_map(items: list[dict]) -> dict[str, bool]:
	if not items:
		return {}

	conditions = []
	values = []
	for item in items:
		level = cint(item.get("class_level"))
		prefix_length = level * CLASS_CODE_SEGMENT_LENGTH
		if (level + 1) * CLASS_CODE_SEGMENT_LENGTH > 8:
			continue
		conditions.append("(class_level = %s AND LEFT(class_code, %s) = %s)")
		values.extend([level + 1, prefix_length, normalize_class_code(item["class_code"])[:prefix_length]])

	if not conditions:
		return {item["class_code"]: False for item in items}

	rows = frappe.db.sql(
		f"""
		SELECT class_level, LEFT(class_code, 8) AS class_code
		FROM `tab{CLASSIFICATION_DOCTYPE}`
		WHERE is_active = 1
			AND ({" OR ".join(conditions)})
		""",
		values,
		as_dict=True,
	)

	child_keys = {
		(cint(row.class_level) - 1, normalize_class_code(row.class_code)[: (cint(row.class_level) - 1) * 2])
		for row in rows
	}
	return {
		item["class_code"]: (
			(cint(item.get("class_level")), normalize_class_code(item["class_code"])[: cint(item.get("class_level")) * 2])
			in child_keys
		)
		for item in items
	}


def _build_ancestor_paths(items: list[dict]) -> dict[str, list[dict]]:
	if not items:
		return {}

	path_codes: set[str] = set()
	item_codes: dict[str, tuple[str, int]] = {}
	for item in items:
		code = normalize_class_code(item["class_code"])
		level = cint(item.get("class_level"))
		item_codes[code] = (code, level)
		path_codes.update(ancestor_codes_for(code, level))

	ancestors = frappe.get_all(
		CLASSIFICATION_DOCTYPE,
		filters={"class_code": ["in", list(path_codes)]},
		fields=["class_code", "class_name", "class_level"],
	)
	by_code = {row.class_code: row for row in ancestors}
	paths = {}
	for code, (_, level) in item_codes.items():
		path = []
		for ancestor_code in ancestor_codes_for(code, level):
			ancestor = by_code.get(ancestor_code)
			path.append(
				{
					"class_code": ancestor_code,
					"class_name": ancestor.class_name if ancestor else None,
					"class_level": cint(ancestor.class_level) if ancestor else len(path) + 1,
					"missing": ancestor is None,
				}
			)
		paths[code] = path
	return paths


def _paged_result(items: list[dict], page_size: int) -> tuple[list[dict], dict]:
	has_next = len(items) > page_size
	page_items = items[:page_size]
	return page_items, {
		"page_size": page_size,
		"has_next": has_next,
		"next_cursor": encode_cursor(page_items[-1]["class_code"]) if has_next else None,
	}


def get_classification_children(parent_code=None, page_size=50, cursor=None):
	page_size = clamp_page_size(page_size)
	after_code = decode_cursor(cursor)

	if parent_code:
		parent_code = normalize_class_code(parent_code)
		parent = frappe.db.get_value(
			CLASSIFICATION_DOCTYPE,
			{"class_code": parent_code, "is_active": 1},
			["class_code", "class_level"],
			as_dict=True,
		)
		if not parent:
			raise frappe.DoesNotExistError(f"Classification {parent_code} not found.")
		child_level = cint(parent.class_level) + 1
		prefix = parent_code[: cint(parent.class_level) * CLASS_CODE_SEGMENT_LENGTH]
		filters = [
			["class_level", "=", child_level],
			["class_code", "like", f"{prefix}%"],
			["is_active", "=", 1],
		]
	else:
		filters = [["class_level", "=", 1], ["is_active", "=", 1]]

	if after_code:
		filters.append(["class_code", ">", after_code])

	items = frappe.get_all(
		CLASSIFICATION_DOCTYPE,
		filters=filters,
		fields=CLASSIFICATION_FIELDS,
		order_by="class_code asc",
		limit_page_length=page_size + 1,
	)

	items, pagination = _paged_result(items, page_size)
	has_children = _has_children_map(items)
	result = [
		_serialize_classification(
			item,
			has_children.get(item["class_code"], False),
		)
		for item in items
	]
	return result, pagination


def search_classifications(search, page_size=30, cursor=None):
	search = str(search or "").strip()
	if not search:
		return [], {"page_size": clamp_page_size(page_size), "has_next": False, "next_cursor": None}

	page_size = clamp_page_size(page_size, default=30)
	after_code = decode_cursor(cursor)
	or_filters = [
		["class_code", "like", f"%{search}%"],
		["class_name", "like", f"%{search}%"],
	]
	items = frappe.get_all(
		CLASSIFICATION_DOCTYPE,
		filters={"is_active": 1, **({"class_code": [">", after_code]} if after_code else {})},
		or_filters=or_filters,
		fields=CLASSIFICATION_FIELDS,
		order_by="class_code asc",
		limit_page_length=page_size + 1,
	)
	items, pagination = _paged_result(items, page_size)
	paths = _build_ancestor_paths(items)
	has_children = _has_children_map(items)
	result = []
	for item in items:
		serialized = _serialize_classification(item)
		serialized["path"] = paths.get(item["class_code"], [])
		serialized["has_children"] = has_children.get(item["class_code"], False)
		result.append(serialized)
	return result, pagination

def get_classifications(filters=None, page=1, page_size=20, search=None):
    filters = filters or {}
    # data = trigger_zra_select_items_class()
    # if data:
    #     return data, len(data), 1
    allowed_filters = {
        key: filters.get(key)
        for key in ["class_code", "class_level", "is_active"]
        if filters.get(key) is not None
    }

    frappe_filters = build_classification_filters(allowed_filters)
    
    order_by = "class_level asc"
    if filters.get("sort_by"):
        order_by = f"{filters.get('sort_by')} {filters.get('sort_order') or 'asc'}"

    or_filters = []
    if search:
        search = str(search).strip()
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["class_code", "like", f"%{search}%"],
            ["class_name", "like", f"%{search}%"],
        ]

    start = (page - 1) * page_size

    classifications = frappe.get_all(
        "Custom Item Classification",
        filters=frappe_filters,
        or_filters=or_filters if search else None,
        fields=[
            "name as id",
            "class_code",
            "class_name",
            "class_level",
            "is_active",
            # "creation",
            # "modified"
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by=order_by,
    )

    total_records = len(
        frappe.get_all(
            "Custom Item Classification",
            filters=frappe_filters,
            or_filters=or_filters if search else None,
            pluck="name",
        )
    )

    total_pages = (total_records + page_size - 1) // page_size

    for item in classifications:
        item["is_active"] = bool(item.get("is_active"))
        item["class_level"] = cint(item.get("class_level"))

    return classifications, total_records, total_pages


def delete_classification(classification_id: str):
    frappe.delete_doc("Custom Item Classification", classification_id, ignore_permissions=True)
