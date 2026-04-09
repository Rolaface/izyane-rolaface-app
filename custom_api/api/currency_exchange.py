import math
import frappe
from custom_api.utils.response import send_response


def _format_currency(value):
    if value is None:
        return 0.0
    try:
        return round(float(value), 7)
    except Exception:
        return 0.0


def _get_arg(key, default=None):
    return frappe.request.args.get(key, default)


def _get_request_data():
    try:
        if (
            hasattr(frappe, "request")
            and frappe.request
            and getattr(frappe.request, "data", None)
        ):
            data_str = frappe.request.data.decode("utf-8")
            parsed_data = frappe.parse_json(data_str)

            if isinstance(parsed_data, dict):
                return parsed_data

    except Exception:
        pass

    return frappe.local.form_dict or {}


def _format_currency_doc(doc):
    return {
        "id": doc.name,
        "date": doc.date,
        "from_currency": doc.from_currency,
        "to_currency": doc.to_currency,
        "exchange_rate": float(doc.exchange_rate) if doc.exchange_rate else 0.0,
        "purpose": {
            "for_buying": bool(doc.for_buying),
            "for_selling": bool(doc.for_selling),
        },
        "timestamps": {"created_at": doc.creation, "modified_at": doc.modified},
    }


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_currency_exchanges():
    search_term = _get_arg("search", "").strip().lower()
    from_currency = _get_arg("from_currency")
    to_currency = _get_arg("to_currency")
    date = _get_arg("date")
    for_buying = _get_arg("for_buying")
    for_selling = _get_arg("for_selling")

    page = int(_get_arg("page", 1))
    page_size = int(_get_arg("page_size", 100))

    start = (page - 1) * page_size

    filters = {}

    if from_currency:
        filters["from_currency"] = from_currency.upper()
    if to_currency:
        filters["to_currency"] = to_currency.upper()
    if date:
        filters["date"] = date

    if for_buying is not None:
        filters["for_buying"] = int(for_buying)

    if for_selling is not None:
        filters["for_selling"] = int(for_selling)

    or_filters = []
    if search_term:
        or_filters = [
            ["name", "like", f"%{search_term}%"],
            ["from_currency", "like", f"%{search_term}%"],
            ["to_currency", "like", f"%{search_term}%"],
        ]

    fields = [
        "name",
        "date",
        "from_currency",
        "to_currency",
        "exchange_rate",
        "for_buying",
        "for_selling",
        "creation",
        "modified",
    ]

    # FIX for Frappe v16: Using UPPERCASE dictionary syntax for aggregate function
    count_result = frappe.get_all(
        "Currency Exchange",
        filters=filters,
        or_filters=or_filters,
        fields=[{"COUNT": "name"}],
        as_list=True,
    )
    total_items = count_result[0][0] if count_result and count_result[0] else 0

    raw_data = frappe.get_all(
        "Currency Exchange",
        filters=filters,
        or_filters=or_filters,
        fields=fields,
        order_by="date desc, name desc",
        limit_start=start,
        limit_page_length=page_size,
    )

    rows = []
    for row in raw_data:
        rows.append(
            {
                "id": row.get("name"),
                "date": row.get("date"),
                "from_currency": row.get("from_currency"),
                "to_currency": row.get("to_currency"),
                "exchange_rate": _format_currency(row.get("exchange_rate")),
                "purpose": {
                    "for_buying": bool(row.get("for_buying")),
                    "for_selling": bool(row.get("for_selling")),
                },
                "timestamps": {
                    "created_at": row.get("creation"),
                    "modified_at": row.get("modified"),
                },
            }
        )

    total_pages = math.ceil(total_items / page_size) if page_size else 1

    pagination = {
        "page": page,
        "page_size": page_size,
        "items_in_page": len(rows),
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }

    return send_response(
        status="success",
        message="Currency Exchange rates fetched successfully.",
        data={
            "data": rows,
            "pagination": pagination,
        },
        status_code=200,
        http_status=200,
    )


# ==========================================
# 1. GET BY ID (READ)
# ==========================================
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_currency_exchange(id):
    if not id:
        return send_response(
            status="error",
            message="Record ID (id) is required.",
            status_code=400,
            http_status=400,
        )

    if not frappe.db.exists("Currency Exchange", id):
        return send_response(
            status="error",
            message=f"Currency Exchange '{id}' not found.",
            status_code=404,
            http_status=404,
        )

    try:
        doc = frappe.get_doc("Currency Exchange", id)

        return send_response(
            status="success",
            message="Record fetched successfully.",
            data=_format_currency_doc(doc),
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        return send_response(
            status="error", message=str(e), status_code=500, http_status=500
        )


# ==========================================
# 2. CREATE (POST)
# ==========================================
@frappe.whitelist(allow_guest=False, methods=["POST"])
def create_currency_exchange():
    data = _get_request_data()

    required_fields = ["from_currency", "to_currency", "exchange_rate", "date"]
    missing = [f for f in required_fields if not data.get(f)]
    if missing:
        return send_response(
            status="error",
            message=f"Missing required fields: {', '.join(missing)}",
            status_code=400,
            http_status=400,
        )

    if data.get("from_currency") == data.get("to_currency"):
        return send_response(
            status="error",
            message="From and To currencies cannot be the same.",
            status_code=400,
            http_status=400,
        )

    try:
        doc = frappe.get_doc(
            {
                "doctype": "Currency Exchange",
                "date": data.get("date"),
                "from_currency": data.get("from_currency").upper(),
                "to_currency": data.get("to_currency").upper(),
                "exchange_rate": float(data.get("exchange_rate")),
                "for_buying": int(data.get("for_buying", 1)),
                "for_selling": int(data.get("for_selling", 1)),
            }
        )

        doc.insert(ignore_permissions=False)
        frappe.db.commit()
        return send_response(
            status="success",
            message="Currency Exchange created successfully.",
            data=_format_currency_doc(doc),
            status_code=201,  # 201 Created
            http_status=201,
        )
    except frappe.UniqueValidationError:
        frappe.db.rollback()
        return send_response(
            status="error",
            message="A record with these details already exists.",
            status_code=409,
            http_status=409,
        )
    except Exception as e:
        frappe.db.rollback()
        return send_response(
            status="error", message=str(e), status_code=500, http_status=500
        )


# ==========================================
# 3. UPDATE (PUT / PATCH)
# ==========================================
@frappe.whitelist(allow_guest=False, methods=["POST", "PUT", "PATCH"])
def update_currency_exchange(id=None, **kwargs):
    data = _get_request_data()

    record_name = id or data.get("id") or _get_arg("id")

    if not record_name:
        return send_response(
            status="error",
            message="Record ID (id) is required.",
            status_code=400,
            http_status=400,
        )

    if not frappe.db.exists("Currency Exchange", record_name):
        return send_response(
            status="error",
            message=f"Currency Exchange '{record_name}' not found.",
            status_code=404,
            http_status=404,
        )

    update_data = {k: v for k, v in data.items() if k != "name"}

    if not update_data:
        return send_response(
            status="error",
            message="No data provided for update.",
            status_code=400,
            http_status=400,
        )

    try:
        doc = frappe.get_doc("Currency Exchange", record_name)

        updatable_fields = [
            "date",
            "exchange_rate",
            "for_buying",
            "for_selling",
            "from_currency",
            "to_currency",
        ]

        for field in updatable_fields:
            if field in update_data:
                val = update_data.get(field)
                if field in ["from_currency", "to_currency"] and isinstance(val, str):
                    val = val.upper()
                doc.set(field, val)

        doc.save(ignore_permissions=False)
        frappe.db.commit()

        return send_response(
            status="success",
            message="Currency Exchange updated successfully.",
            data=_format_currency_doc(doc),
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.db.rollback()
        return send_response(
            status="error", message=str(e), status_code=500, http_status=500
        )


# ==========================================
# 4. DELETE (DELETE)
# ==========================================
@frappe.whitelist(allow_guest=False, methods=["DELETE"])
def delete_currency_exchange(id):
    if not id:
        return send_response(
            status="error",
            message="Record ID (id) is required.",
            status_code=400,
            http_status=400,
        )

    if not frappe.db.exists("Currency Exchange", id):
        return send_response(
            status="error",
            message=f"Currency Exchange '{id}' not found.",
            status_code=404,
            http_status=404,
        )

    try:
        frappe.delete_doc("Currency Exchange", id, ignore_permissions=False)
        frappe.db.commit()

        return send_response(
            status="success",
            message=f"Currency Exchange '{id}' deleted successfully.",
            data={"id": id},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.db.rollback()
        return send_response(
            status="error", message=str(e), status_code=500, http_status=500
        )