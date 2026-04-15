import frappe
from frappe.utils import flt
from .utils import build_journal_entry_filters

def create_journal_entry(data):
    company = data.get("company") or frappe.defaults.get_user_default("Company")
    
    if not company:
        frappe.throw("Company is required and no default company is set.")

    is_opening = data.get("isOpening")
    if str(is_opening).lower() in ["true", "1", "yes"]:
        is_opening_val = "Yes"
    else:
        is_opening_val = "No"

    doc_args = {
        "doctype": "Journal Entry",
        "company": company,
        "posting_date": data.get("postingDate") or frappe.utils.today(),
        "voucher_type": data.get("voucherType") or "Journal Entry",
        "user_remark": data.get("remark"),
        "reference_date": data.get("referenceDate"),
        "cheque_no": data.get("referenceNumber"),
        "cheque_date": data.get("referenceDate"),
        "is_opening": is_opening_val,
        "multi_currency": 1,
        "accounts": []
    }

    for acc in data.get("accounts", []):
        doc_args["accounts"].append(
            {
                "account": acc.get("account"),
                "account_currency": acc.get("currency"),
                "exchange_rate": flt(acc.get("exchangeRate", 1)),
                "debit_in_account_currency": flt(acc.get("debit")),
                "credit_in_account_currency": flt(acc.get("credit")),
                "party_type": acc.get("partyType"),
                "party": acc.get("party"),
                "cost_center": acc.get("costCenter"),
                "project": acc.get("project"),
                "user_remark": acc.get("remark")
            }
        )

    jv = frappe.get_doc(doc_args).insert(ignore_permissions=True)
    return jv

def update_journal_entry(jv_id, data):
    jv = frappe.get_doc("Journal Entry", jv_id)

    if jv.docstatus == 1:
        raise frappe.ValidationError("Cannot edit a submitted Journal Entry. Cancel it first.")

    field_map = {
        "company": "company",
        "postingDate": "posting_date",
        "voucherType": "voucher_type",
        "remark": "user_remark",
        "referenceNumber": "cheque_no",
        "referenceDate": "cheque_date",
    }

    for k, v in field_map.items():
        if data.get(k) is not None:
            setattr(jv, v, data.get(k))

    if data.get("isOpening") is not None:
        if str(data.get("isOpening")).lower() in ["true", "1", "yes"]:
            jv.is_opening = "Yes"
        else:
            jv.is_opening = "No"

    jv.multi_currency = 1

    if "accounts" in data:
        jv.set("accounts", [])
        for acc in data.get("accounts"):
            jv.append(
                "accounts",
                {
                    "account": acc.get("account"),
                    "account_currency": acc.get("currency"),
                    "exchange_rate": flt(acc.get("exchangeRate", 1)),
                    "debit_in_account_currency": flt(acc.get("debit")),
                    "credit_in_account_currency": flt(acc.get("credit")),
                    "party_type": acc.get("partyType"),
                    "party": acc.get("party"),
                    "cost_center": acc.get("costCenter"),
                    "project": acc.get("project"),
                    "user_remark": acc.get("remark")
                },
            )

    jv.save(ignore_permissions=True)
    return jv

def get_journal_entry_by_id(jv_id):
    jv = frappe.get_doc("Journal Entry", jv_id)
    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

    data = {
        "id": jv.name,
        "company": jv.company,
        "postingDate": jv.posting_date,
        "voucherType": jv.voucher_type,
        "remark": jv.user_remark,
        "referenceNumber": jv.cheque_no,
        "referenceDate": jv.cheque_date,
        "isOpening": True if jv.is_opening == "Yes" else False,
        "status": status_map.get(jv.docstatus, "Draft"),
        "docstatus": jv.docstatus,
        "totalDebit": jv.total_debit,
        "totalCredit": jv.total_credit,
        "difference": jv.difference,
        "multiCurrency": jv.multi_currency,
        "accounts": []
    }

    for acc in jv.accounts:
        data["accounts"].append(
            {
                "account": acc.account,
                "currency": acc.account_currency,
                "exchangeRate": acc.exchange_rate,
                "debit": acc.debit_in_account_currency,
                "credit": acc.credit_in_account_currency,
                "partyType": acc.party_type,
                "party": acc.party,
                "costCenter": acc.cost_center,
                "project": acc.project,
                "remark": acc.user_remark
            }
        )

    return data

def get_journal_entries(filters=None, page=1, page_size=20, search=None):
    filters = filters or {}

    allowed_filters = {
        key: filters.get(key)
        for key in ["status", "from_date", "to_date", "voucherType", "referenceNumber", "isOpening"]
        if filters.get(key) is not None
    }

    frappe_filters = build_journal_entry_filters(allowed_filters)

    or_filters = []
    if search:
        search = str(search).strip()
        or_filters = [
            ["name", "like", f"%{search}%"],
            ["voucher_type", "like", f"%{search}%"],
            ["user_remark", "like", f"%{search}%"],
            ["cheque_no", "like", f"%{search}%"]
        ]

    start = (page - 1) * page_size

    entries = frappe.get_all(
        "Journal Entry",
        filters=frappe_filters,
        or_filters=or_filters if search else None,
        fields=[
            "name",
            "posting_date",
            "voucher_type",
            "total_debit",
            "total_credit",
            "difference",
            "is_opening",
            "docstatus"
        ],
        limit_start=start,
        limit_page_length=page_size,
        order_by="creation desc",
    )

    total_entries = len(
        frappe.get_all(
            "Journal Entry",
            filters=frappe_filters,
            or_filters=or_filters if search else None,
            pluck="name",
        )
    )

    total_pages = (total_entries + page_size - 1) // page_size
    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

    for entry in entries:
        entry["id"] = entry.pop("name")
        entry["postingDate"] = entry.pop("posting_date")
        entry["voucherType"] = entry.pop("voucher_type")
        entry["totalDebit"] = entry.pop("total_debit")
        entry["totalCredit"] = entry.pop("total_credit")
        entry["difference"] = entry.pop("difference")
        entry["isOpening"] = True if entry.pop("is_opening") == "Yes" else False
        entry["status"] = status_map.get(entry.get("docstatus"), "Draft")

    return entries, total_entries, total_pages

def delete_journal_entry(jv_id):
    jv = frappe.get_doc("Journal Entry", jv_id)
    if jv.docstatus == 1:
        raise frappe.ValidationError("Cannot delete a submitted Journal Entry. Cancel it first.")

    frappe.delete_doc("Journal Entry", jv_id, ignore_permissions=True)

def update_journal_entry_status(jv_id, action):
    jv = frappe.get_doc("Journal Entry", jv_id)
    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}

    if not frappe.has_permission("Journal Entry", "write", jv):
        raise frappe.PermissionError("No permission to modify this entry")

    if action == "approved":
        if jv.docstatus == 1:
            raise frappe.ValidationError("Entry is already approved.")
        if jv.docstatus == 2:
            raise frappe.ValidationError("Cannot approve a cancelled entry. Please amend it first.")
        jv.submit()
        return {"id": jv.name, "status": status_map.get(jv.docstatus), "docstatus": jv.docstatus}

    elif action == "cancelled":
        if jv.docstatus == 2:
            raise frappe.ValidationError("Entry is already cancelled.")
        if jv.docstatus == 0:
            raise frappe.ValidationError("Cannot cancel a Draft entry. Submit it first.")
        jv.cancel()
        return {"id": jv.name, "status": status_map.get(jv.docstatus), "docstatus": jv.docstatus}

    elif action == "amend":
        if jv.docstatus == 0:
            raise frappe.ValidationError("Entry is already in Draft state.")
        if jv.docstatus == 1:
            raise frappe.ValidationError("Cannot amend an approved entry. Cancel it first.")
        amended_doc = frappe.copy_doc(jv)
        amended_doc.amended_from = jv.name
        amended_doc.docstatus = 0
        amended_doc.insert()
        return {"id": amended_doc.name, "status": status_map.get(amended_doc.docstatus), "docstatus": amended_doc.docstatus}

    else:
        raise frappe.ValidationError("Invalid action. Allowed: approved, cancelled, amend")