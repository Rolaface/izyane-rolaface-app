import base64
import json
from typing import Any, Dict

import frappe


CLASS_CODE_LENGTH = 8
CLASS_CODE_SEGMENT_LENGTH = 2
MAX_CLASSIFICATION_PAGE_SIZE = 100


def normalize_class_code(class_code: Any) -> str:
    """Return a validated ZRA class code without changing its leading zeroes."""
    code = str(class_code or "").strip()
    if len(code) != CLASS_CODE_LENGTH or not code.isdigit():
        raise frappe.ValidationError(
            f"class_code must be a {CLASS_CODE_LENGTH}-digit numeric code."
        )
    return code


def parent_code_for(class_code: str, class_level: int) -> str | None:
    """Derive the immediate parent code from ZRA's two-digit code segments."""
    code = normalize_class_code(class_code)
    level = int(class_level or 0)
    if level <= 1:
        return None

    prefix_length = (level - 1) * CLASS_CODE_SEGMENT_LENGTH
    if prefix_length >= CLASS_CODE_LENGTH:
        raise frappe.ValidationError(f"Invalid class_level {level} for class_code {code}.")
    return code[:prefix_length].ljust(CLASS_CODE_LENGTH, "0")


def ancestor_codes_for(class_code: str, class_level: int) -> list[str]:
    """Return canonical root-to-node codes for a classification."""
    code = normalize_class_code(class_code)
    level = int(class_level or 0)
    if level < 1 or level * CLASS_CODE_SEGMENT_LENGTH > CLASS_CODE_LENGTH:
        raise frappe.ValidationError(f"Invalid class_level {level} for class_code {code}.")

    return [
        code[:current_level * CLASS_CODE_SEGMENT_LENGTH].ljust(CLASS_CODE_LENGTH, "0")
        for current_level in range(1, level + 1)
    ]


def encode_cursor(class_code: str) -> str:
    payload = json.dumps({"class_code": normalize_class_code(class_code)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        return normalize_class_code(payload["class_code"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise frappe.ValidationError("Invalid pagination cursor.") from exc


def clamp_page_size(page_size: Any, default: int = 50) -> int:
    try:
        requested = int(page_size)
    except (TypeError, ValueError):
        requested = default
    if requested < 1:
        raise frappe.ValidationError("page_size must be a positive integer.")
    return min(requested, MAX_CLASSIFICATION_PAGE_SIZE)


def validate_classification_payload(data: Dict[str, Any], is_update=False):
    if not is_update:
        if not data.get("class_code"):
            raise frappe.ValidationError("class_code is required.")
        if not data.get("class_name"):
            raise frappe.ValidationError("class_name is required.")

        if frappe.db.exists("Custom Item Classification", {"class_code": data.get("class_code")}):
            raise frappe.ValidationError(f"Custom Item Classification with class_code '{data.get('class_code')}' already exists.")

    if is_update and data.get("class_code"):
        existing = frappe.db.exists("Custom Item Classification", {"class_code": data.get("class_code")})
        if existing and existing != data.get("id"):
            raise frappe.ValidationError(f"Custom Item Classification with class_code '{data.get('class_code')}' already exists.")


def build_classification_filters(args: Dict[str, Any]) -> dict:
    frappe_filters = {}

    if not args:
        return frappe_filters

    if args.get("class_code"):
        frappe_filters["class_code"] = args["class_code"]

    if args.get("class_level") is not None:
        try:
            frappe_filters["class_level"] = int(args["class_level"])
        except ValueError:
            pass

    if args.get("is_active") is not None:
        val = str(args.get("is_active")).lower()
        frappe_filters["is_active"] = 1 if val in ["true", "1", "yes"] else 0

    return frappe_filters

def transform_item_classes(item_list):
    return [
        {
            "id": item.get("itemClsCd"),
            "class_code": item.get("itemClsCd"),
            "class_name": item.get("itemClsNm"),
            "class_level": item.get("itemClsLvl"),
            # "tax_type_code": item.get("taxTyCd"),
            # "major_target": item.get("mjrTgYn"),
            "is_active": item.get("useYn") == "Y",
        }
        for item in item_list
    ]
def trigger_zra_select_items_class():
    installed_apps = frappe.get_installed_apps()
    if "zra_smart_invoice" in installed_apps:
        try:
            from zra_smart_invoice.client import make_vsdc_request
            from zra_smart_invoice.config import get_zra_config
            config = get_zra_config()
            payload = {}
            payload["tpin"] = config["tpin"]
            payload["bhfId"] = config["bhf_id"]
            payload["lastReqDt"] = "20231215000000"
            result = make_vsdc_request("itemClass/selectItemsClass", payload)
            if result.get('resultCd') == '000':
                data = result.get("data")
                item_list = data.get("itemClsList")
                return transform_item_classes(item_list)
                # return data
        except Exception as e:
            frappe.log_error("trigger_zra_select_items_class Exception", str(e))
