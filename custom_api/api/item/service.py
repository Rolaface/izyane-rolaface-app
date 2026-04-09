from custom_api.api.item.brand_service import get_or_create_brand
from custom_api.api.item.price_service import create_item_prices
from custom_api.api.item.utils.item_utils import map_item_response, map_to_frappe_item, validate_item_payload
import frappe

def create_item_service(data: dict):
    
    validate_item_payload(data)

    brand = get_or_create_brand(data.get("brand"))
    
    item_doc_dict = map_to_frappe_item(data, brand)
    

    item_doc = frappe.get_doc(item_doc_dict)

    item_doc.insert(ignore_permissions=True)

    create_item_prices(item_doc, data)

    frappe.db.commit()

    return item_doc

def get_items_service(params):

    page = int(params.get("page", 1))
    page_size = int(params.get("page_size", 10))

    filters = _build_filters(params)

    # Fetch Items
    items = frappe.get_all(
        "Item",
        filters=filters,
        fields=[
            "name",
            "item_name",
            "item_group",
            "stock_uom",
            "description",
            "brand",
            "weight_per_unit",
            "weight_uom",
            "valuation_method",
            "has_batch_no",
            "has_expiry_date"
        ],
        limit_start=(page - 1) * page_size,
        limit_page_length=page_size
    )

    total_count = frappe.db.count("Item", filters=filters)

    # Map response
    data = [map_item_response(item) for item in items]

    return {
        "data": data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_records": total_count,
            "total_pages": (total_count // page_size) + (1 if total_count % page_size else 0)
        }
    }


def _build_filters(params):
    filters = {}

    if params.get("item_code"):
        filters["name"] = ["like", f"%{params.get('item_code')}%"]

    if params.get("item_name"):
        filters["item_name"] = ["like", f"%{params.get('item_name')}%"]

    if params.get("item_group"):
        filters["item_group"] = params.get("item_group")

    if params.get("brand"):
        filters["brand"] = params.get("brand")

    return filters