import frappe
from typing import Dict, Any

def validate_journal_entry_payload(data: Dict[str, Any], is_update=False):
    is_opening = data.get("isOpening")
    if is_opening is not None:
        if str(is_opening).lower() not in ["true", "false", "1", "0", "yes", "no"]:
            raise frappe.ValidationError("isOpening must be a boolean or 'Yes'/'No'.")

    accounts = data.get("accounts")
    if accounts is not None:
        if not isinstance(accounts, list) or len(accounts) == 0:
            raise frappe.ValidationError("At least one account row is required in the 'accounts' array.")

        total_debit = 0.0
        total_credit = 0.0

        for idx, acc in enumerate(accounts):
            if not acc.get("account"):
                raise frappe.ValidationError(f"Row {idx+1}: account is required.")
            
            if acc.get("partyType") and not acc.get("party"):
                raise frappe.ValidationError(f"Row {idx+1}: 'party' is required when 'partyType' is specified.")
            
            try:
                debit = float(acc.get("debit") or 0)
                credit = float(acc.get("credit") or 0)
            except ValueError:
                raise frappe.ValidationError(f"Row {idx+1}: debit and credit must be valid numbers.")
            
            if debit == 0 and credit == 0:
                raise frappe.ValidationError(f"Row {idx+1}: Either debit or credit must be greater than 0.")
            if debit > 0 and credit > 0:
                raise frappe.ValidationError(f"Row {idx+1}: Cannot have both debit and credit amounts in the same row.")
            if debit < 0 or credit < 0:
                raise frappe.ValidationError(f"Row {idx+1}: Debit and credit amounts cannot be negative.")
                
            total_debit += debit
            total_credit += credit

def build_journal_entry_filters(args):
    frappe_filters = {}

    if not args:
        return frappe_filters

    if args.get("company"):
        frappe_filters["company"] = args["company"]

    if args.get("status"):
        status_map = {"draft": 0, "submitted": 1, "approved": 1, "cancelled": 2}
        statuses = args["status"] if isinstance(args["status"], list) else [args["status"]]
        docstatuses = [status_map.get(str(s).lower(), 0) for s in statuses]
        frappe_filters["docstatus"] = ["in", docstatuses]

    if args.get("voucherType"):
        frappe_filters["voucher_type"] = args["voucherType"]
        
    if args.get("referenceNumber"):
        frappe_filters["cheque_no"] = ["like", f"%{args['referenceNumber']}%"]

    if args.get("from_date") and args.get("to_date"):
        frappe_filters["posting_date"] = ["between", [args["from_date"], args["to_date"]]]
        
    if args.get("isOpening") is not None:
        val = str(args.get("isOpening")).lower()
        if val in ["true", "1", "yes"]:
            frappe_filters["is_opening"] = "Yes"
        elif val in ["false", "0", "no"]:
            frappe_filters["is_opening"] = "No"

    return frappe_filters