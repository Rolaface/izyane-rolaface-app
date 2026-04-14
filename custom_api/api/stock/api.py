import json
# from erpnext.zra_client.main import ZRAClient
# from erpnext.zra_client.generic_api import send_response
from frappe.utils.data import flt
from datetime import datetime
import frappe

from collections import defaultdict
from custom_api.utils.response import send_response

# from erpnext.zra_client.custom_frappe_client import CustomFrappeClient
# CUSTOM_FRAPPE_INSTANCE = CustomFrappeClient()

# ZRA_CLIENT = ZRAClient()

# def get_item_details(item_code):
#     if not item_code:
#         return send_response(
#             status="fail",
#             message="Item code is required.",
#             status_code=400,
#             http_status=400
#         )
    
#     try:
#         item = frappe.get_doc("Item", item_code)
#     except frappe.DoesNotExistError:
#         return send_response(
#             status="fail",
#             message="Item not found",
#             status_code=404,
#             http_status=404
#         )
#     except Exception as e:
#         return send_response(
#             status="fail",
#             message=f"Cannot proceed: {str(e)}",
#             status_code=400,
#             http_status=400
#         )
    
#     itemName = item.item_name
#     itemClassCd = getattr(item, "custom_itemclscd", None)
#     itemPackingUnitCd = getattr(item, "custom_pkgunitcd", None)
#     itemUnitCd = getattr(item, "stock_uom", None)

#     return {
#         "itemName": itemName,
#         "itemClassCd": itemClassCd,
#         "itemPackingUnitCd": itemPackingUnitCd,
#         "itemUnitCd": itemUnitCd
#     }


# def validate_item_and_warehouse(item_code, warehouse):
#     if not frappe.db.exists("Item", item_code):
#         return send_response(
#             status="fail",
#             message=f"Item '{item_code}' does not exist",
#             status_code=404,
#             http_status=404
#         )
#     if not frappe.db.exists("Warehouse", warehouse):
#         return send_response(
#             status="fail",
#             message=f"Warehouse '{warehouse}' does not exist",
#             status_code=404,
#             http_status=404
#         )
#     return None


# @frappe.whitelist(allow_guest=False)
# def create_item_stock_api():
#     try:
#         data = json.loads(frappe.request.data)
#         warehouse = data.get("warehouse")
#         items_data = data.get("items", [])

#         if not warehouse:
#             warehouse = "Finished Goods - RI"

#         if not frappe.db.exists("Warehouse", warehouse):
#             return send_response("fail", f"Warehouse '{warehouse}' does not exist", 404, 404)

#         if not items_data:
#             return send_response("fail", "No items provided", 400, 400)

#         # Read ZRA flag from site_config.json
#         enable_zra = frappe.conf.get("enable_zra_sync", False)

#         today = datetime.today().strftime('%Y%m%d')

#         itemList = []
#         totTaxblAmt = totTaxAmt = totAmt = 0
#         stock_items = []

#         for i, item in enumerate(items_data):
#             item_code = item.get("item_code")
#             qty = flt(item.get("qty", 0))
#             price = flt(item.get("price", 0))
#             batch_no = item.get("batch_no")
#             if not item_code or qty <= 0 or price <= 0:
#                 return send_response("fail", f"Invalid data for item {i+1}", 400, 400)

#             item_details = get_item_details(item_code)
#             if not item_details:
#                 return send_response(
#                     status="fail",
#                     message=f"Item '{item_code}' does not exist",
#                     status_code=404,
#                     http_status=404
#                 )

#             splyAmt = round(price * qty, 4)
#             taxblAmt = round(splyAmt / 1.16, 4)
#             vatAmount = round(splyAmt - taxblAmt, 4)
#             totItemAmt = round(splyAmt, 4)

#             totTaxblAmt += taxblAmt
#             totTaxAmt += vatAmount
#             totAmt += totItemAmt

#             itemList.append({
#                 "itemSeq": i + 1,
#                 "itemCd": item_code,
#                 "itemClsCd": item_details.get("itemClassCd"),
#                 "itemNm": item_details.get("itemName"),
#                 "pkgUnitCd": item_details.get("itemPackingUnitCd"),
#                 "qtyUnitCd": item_details.get("itemUnitCd"),
#                 "qty": qty,
#                 "pkg": 1,
#                 "totDcAmt": 0,
#                 "prc": price,
#                 "splyAmt": splyAmt,
#                 "taxblAmt": taxblAmt,
#                 "vatCatCd": "A",
#                 "taxAmt": vatAmount,
#                 "totAmt": totItemAmt
#             })

#             stock_items.append({
#                 "item_code": item_code,
#                 "t_warehouse": warehouse,
#                 "qty": qty,
#                 "basic_rate": price,
#                 "custom_taxable_amount": taxblAmt,
#                 "custom_tax_amount": vatAmount,
#                 "custom_total_amount": totItemAmt,
#                 "batch_no": batch_no
#             })

#         # Default values used when ZRA is disabled
#         org_sar_no = 0
#         reg_ty_cd = "M"
#         sar_ty_cd = "04"

#         # ── ZRA Sync (only when enable_zra_sync = true in site_config.json) ──
#         if enable_zra:
#             PAYLOAD = {
#                 "tpin": ZRA_CLIENT.get_tpin(),
#                 "bhfId": ZRA_CLIENT.get_branch_code(),
#                 "sarNo": 1,
#                 "orgSarNo": 0,
#                 "regTyCd": reg_ty_cd,
#                 "sarTyCd": sar_ty_cd,
#                 "ocrnDt": today,
#                 "totItemCnt": len(itemList),
#                 "totTaxblAmt": round(totTaxblAmt, 4),
#                 "totTaxAmt": round(totTaxAmt, 4),
#                 "totAmt": round(totAmt, 4),
#                 "regrId": frappe.session.user,
#                 "regrNm": frappe.session.user,
#                 "modrNm": frappe.session.user,
#                 "modrId": frappe.session.user,
#                 "itemList": itemList
#             }

#             print(json.dumps(PAYLOAD, indent=4))

#             org_sar_no = 0
#             if frappe.conf.get("enable_zra_sync", False):
#                 result = ZRA_CLIENT.create_item_stock_zra_client(PAYLOAD)
#                 data_result = result.json()
#                 print(data_result)
#                 if data_result.get("resultCd") != "000":
#                     return send_response(
#                         status="fail",
#                         message=data_result.get("resultMsg", "ZRA Stock Sync Failed"),
#                         status_code=400,
#                         data=None,
#                         http_status=400
#                     )

#                 org_sar_no = data_result.get("orgSarNo", 0)

#         # ── Create Batches if batch_no provided ──────────────────────────────
#         for stock_item in stock_items:
#             batch_no = stock_item.get("batch_no")
#             item_code = stock_item.get("item_code")
#             if batch_no and item_code:
#                 if not frappe.db.exists("Batch", batch_no):
#                     batch = frappe.get_doc({
#                         "doctype": "Batch",
#                         "batch_id": batch_no,
#                         "item": item_code
#                     })
#                     batch.insert(ignore_permissions=True)
#                     frappe.db.commit()

#         # ── Create Stock Entry (always runs, ZRA or not) ─────────────────────
#         company = frappe.defaults.get_global_default("company")

#         stock_entry = frappe.get_doc({
#             "doctype": "Stock Entry",
#             "company": company,
#             "stock_entry_type": "Material Receipt",
#             "custom_original_sar_no": org_sar_no,
#             "custom_registration_type_code": reg_ty_cd,
#             "custom_sar_type_code": sar_ty_cd,
#             "custom_total_taxable_amount": round(totTaxblAmt, 4),
#             "difference_account": "Stock Adjustment - " + company,
#             "items": stock_items
#         })

#         stock_entry.insert(ignore_permissions=True)
#         stock_entry.submit()

#         return send_response("success", "Stock created successfully", 201, 201)

#     except frappe.PermissionError:
#         return send_response("fail", "Permission denied", 403, 403)

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Create Item Stock API Error")
#         return send_response("error", f"Failed to create stock: {str(e)}", 500, 500)


# @frappe.whitelist(allow_guest=False)
# def get_all_stock_entries():
#     try:
#         stock_entries_list = []
#         stock_entries = frappe.get_all(
#             "Stock Entry",
#             fields=[
#                 "name",
#                 "posting_date",
#                 "custom_original_sar_no",
#                 "custom_registration_type_code",
#                 "custom_sar_type_code",
#                 "custom_total_taxable_amount",
#             ],
#             order_by="creation desc"
#         )

#         for entry in stock_entries:
#             items = frappe.get_all(
#                 "Stock Entry Detail",
#                 filters={"parent": entry["name"]},
#                 fields=[
#                     "item_code",
#                     "qty",
#                     "basic_rate",
#                     "custom_taxable_amount",
#                     "custom_tax_amount",
#                     "custom_total_amount"
#                 ]
#             )

#             warehouse = frappe.get_value(
#                 "Stock Entry Detail",
#                 {"parent": entry["name"]},
#                 "t_warehouse"
#             )

#             stock_entries_list.append({
#                 "name": entry["name"],
#                 "posting_date": entry["posting_date"],
#                 "custom_original_sar_no": entry["custom_original_sar_no"],
#                 "custom_registration_type_code": entry["custom_registration_type_code"],
#                 "custom_sar_type_code": entry["custom_sar_type_code"],
#                 "custom_total_taxable_amount": entry["custom_total_taxable_amount"],
#                 "warehouse": warehouse,
#                 "items": items
#             })

#         return send_response(
#             status="success",
#             message="",
#             data=stock_entries_list,
#             status_code=200,
#             http_status=200
#         )

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Get Stock Entries Error")
#         return send_response(
#             "error",
#             f"Failed to fetch stock entries: {str(e)}",
#             500,
#             500
#         )


# @frappe.whitelist(allow_guest=False)
# def get_stock_by_id(bin_id=None):
#     if not bin_id:
#         return send_response("fail", "Bin ID is required", 400, 400)

#     try:
#         bin_doc = frappe.get_doc("Bin", bin_id)
#         price = frappe.db.sql("""
#             SELECT IFNULL(SUM(sle.valuation_rate * sle.actual_qty)/NULLIF(SUM(sle.actual_qty),0),0)
#             FROM `tabStock Ledger Entry` sle
#             WHERE sle.item_code=%s AND sle.warehouse=%s
#         """, (bin_doc.item_code, bin_doc.warehouse))
#         price = price[0][0] if price else 0.0

#         data = {
#             "name": bin_doc.name,
#             "item_code": bin_doc.item_code,
#             "warehouse": bin_doc.warehouse,
#             "actual_qty": bin_doc.actual_qty,
#             "reserved_qty": bin_doc.reserved_qty,
#             "ordered_qty": bin_doc.ordered_qty,
#             "price": flt(price)
#         }
#         return send_response("success", "Stock retrieved", data=data, status_code=200, http_status=200)

#     except frappe.DoesNotExistError:
#         return send_response("fail", f"Bin '{bin_id}' does not exist", 404, 404)
#     except Exception as e:
#         return send_response("error", f"Failed to retrieve stock: {str(e)}", 500, 500)


# @frappe.whitelist(allow_guest=False)
# def delete_stock_entry(stock_entry_id=None):
#     if not stock_entry_id:
#         return send_response("fail", "Stock Entry ID is required", 400, 400)

#     try:
#         se_doc = frappe.get_doc("Stock Entry", stock_entry_id)

#         if se_doc.docstatus == 1:
#             se_doc.cancel()
#         se_doc.delete()
#         frappe.db.commit()

#         return send_response(
#             "success",
#             f"Stock Entry '{stock_entry_id}' deleted successfully",
#             200,
#             200
#         )

#     except frappe.DoesNotExistError:
#         return send_response(
#             "fail",
#             f"Stock Entry '{stock_entry_id}' does not exist",
#             404,
#             404
#         )

#     except frappe.PermissionError:
#         return send_response("fail", "Permission denied", 403, 403)

#     except frappe.LinkExistsError as e:
#         return send_response(
#             "fail",
#             "Cannot delete this Stock Entry because it is linked to other records (GL Entry, Accounting, etc.)",
#             400,
#             400
#         )

#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Delete Stock Entry Error")
#         return send_response(
#             "error",
#             f"Failed to delete Stock Entry: {str(e)}",
#             500,
#             500
#         )

# @frappe.whitelist()
# def get_stock_balance(
#     from_date=None,
#     to_date=None,
#     warehouse=None,
#     item_code=None,
#     item_group=None,
#     batch_no=None,
#     page=1,
#     page_size=20,
# ):
#     page      = int(page)
#     page_size = int(page_size)

#     # ── Helper: build base filters ───────────────────────────────────────────
#     def base_filters():
#         f = {
#             "company":      frappe.defaults.get_global_default("company"),
#             "docstatus":    1,
#             "is_cancelled": 0,
#         }
#         if warehouse:  f["warehouse"]  = warehouse
#         if item_code:  f["item_code"]  = item_code
#         if batch_no:   f["batch_no"]   = batch_no
#         return f

#     # ── Step 1: Opening qty (SLE before from_date) ───────────────────────────
#     opening_map = {}

#     if from_date:
#         opening_filters = base_filters()
#         opening_filters["posting_date"] = ("<", from_date)

#         opening_entries = frappe.get_all(
#             "Stock Ledger Entry",
#             filters=opening_filters,
#             fields=[
#                 "item_code", "warehouse", "batch_no",
#                 "qty_after_transaction", "valuation_rate", "stock_value"
#             ],
#             order_by="posting_date asc, posting_time asc",
#             limit=0,
#         )

#         for e in opening_entries:
#             key = (e["item_code"], e["warehouse"], e["batch_no"] or "")
#             opening_map[key] = {
#                 "opening_qty":    e["qty_after_transaction"],
#                 "opening_value":  round(e["stock_value"] or 0, 2),
#                 "valuation_rate": e["valuation_rate"] or 0,
#             }

#     # ── Step 2: Movement entries ─────────────────────────────────────────────
#     range_filters = base_filters()

#     if from_date and to_date:
#         range_filters["posting_date"] = ("between", [from_date, to_date])
#     elif from_date:
#         range_filters["posting_date"] = (">=", from_date)
#     elif to_date:
#         range_filters["posting_date"] = ("<=", to_date)

#     range_entries = frappe.get_all(
#         "Stock Ledger Entry",
#         filters=range_filters,
#         fields=[
#             "item_code", "warehouse", "batch_no",
#             "actual_qty", "qty_after_transaction",
#             "valuation_rate", "stock_value", "stock_value_difference",
#             "voucher_type",
#         ],
#         order_by="posting_date asc, posting_time asc",
#         limit=0,
#     )

#     # ── Step 3: Calculate per (item, warehouse, batch) ───────────────────────
#     movement = defaultdict(lambda: {
#         "in_qty":              0.0,
#         "in_value":            0.0,
#         "out_qty":             0.0,
#         "out_value":           0.0,
#         "buy_value":           0.0,
#         "sell_value":          0.0,
#         "last_qty_after":      0.0,
#         "last_valuation_rate": 0.0,
#         "last_stock_value":    0.0,
#     })

#     for e in range_entries:
#         key      = (e["item_code"], e["warehouse"], e["batch_no"] or "")
#         m        = movement[key]
#         val_diff = e["stock_value_difference"] or 0

#         m["last_qty_after"]      = e["qty_after_transaction"]
#         m["last_valuation_rate"] = e["valuation_rate"] or 0
#         m["last_stock_value"]    = e["stock_value"] or 0

#         if e["actual_qty"] > 0:
#             m["in_qty"]    += e["actual_qty"]
#             m["in_value"]  += val_diff
#             m["buy_value"] += val_diff
#         else:
#             m["out_qty"]    += abs(e["actual_qty"])
#             m["out_value"]  += abs(val_diff)
#             m["sell_value"] += abs(val_diff)

#     # ── Step 4: Fetch item_name, item_group, stock_uom from Item doctype ─────
#     all_item_codes = list({key[0] for key in set(opening_map.keys()) | set(movement.keys())})

#     item_details_map = {}
#     if all_item_codes:
#         item_details = frappe.get_all(
#             "Item",
#             filters=[["item_code", "in", all_item_codes]],
#             fields=["item_code", "item_name", "item_group", "stock_uom"],  # ← item_name field
#             limit=0,
#         )
#         for item in item_details:
#             item_details_map[item["item_code"]] = {
#                 "item_name":  item["item_name"],   # ← actual name like "dfetyde"
#                 "item_group": item["item_group"],
#                 "stock_uom":  item["stock_uom"],
#             }

#     # ── Step 5: Group by (item_code, warehouse) → collect batch_no as list ───
#     all_keys  = set(opening_map.keys()) | set(movement.keys())

#     # key: (item_code, warehouse) → item row
#     items_map = {}

#     for (code, wh, batch) in sorted(all_keys):
#         o = opening_map.get((code, wh, batch), {
#             "opening_qty":    0.0,
#             "opening_value":  0.0,
#             "valuation_rate": 0.0,
#         })
#         m = movement.get((code, wh, batch), {
#             "in_qty":              0.0,
#             "in_value":            0.0,
#             "out_qty":             0.0,
#             "out_value":           0.0,
#             "buy_value":           0.0,
#             "sell_value":          0.0,
#             "last_valuation_rate": 0.0,
#             "last_stock_value":    0.0,
#         })
#         item_info = item_details_map.get(code, {
#             "item_name":  "",
#             "item_group": "",
#             "stock_uom":  "",
#         })

#         if item_group and item_info.get("item_group") != item_group:
#             continue

#         item_key = (code, wh)

#         if item_key not in items_map:
#             # initialize item row
#             items_map[item_key] = {
#                 "item_code":      code,
#                 "item_name":      item_info.get("item_name", ""),  # ← actual item name
#                 "item_group":     item_info.get("item_group", ""),
#                 "warehouse":      wh,
#                 "stock_uom":      item_info.get("stock_uom", ""),
#                 "batch_no":       [],     # ← start as empty list
#                 "opening_qty":    0.0,
#                 "opening_value":  0.0,
#                 "in_qty":         0.0,
#                 "in_value":       0.0,
#                 "out_qty":        0.0,
#                 "out_value":      0.0,
#                 "bal_qty":        0.0,
#                 "bal_val":        0.0,
#                 "valuation_rate": 0.0,
#                 "buy_value":      0.0,
#                 "sell_value":     0.0,
#             }

#         row = items_map[item_key]

#         # collect batch_no into list
#         if batch:
#             row["batch_no"].append(batch)

#         # accumulate totals across all batches
#         opening_qty   = o["opening_qty"]
#         opening_value = o["opening_value"]
#         in_qty        = m["in_qty"]
#         in_value      = m["in_value"]
#         out_qty       = m["out_qty"]
#         out_value     = m["out_value"]
#         buy_value     = m["buy_value"]
#         sell_value    = m["sell_value"]
#         bal_qty       = opening_qty + in_qty - out_qty
#         val_rate      = m["last_valuation_rate"] or o["valuation_rate"]
#         bal_val       = bal_qty * val_rate

#         row["opening_qty"]    += opening_qty
#         row["opening_value"]  += opening_value
#         row["in_qty"]         += in_qty
#         row["in_value"]       += in_value
#         row["out_qty"]        += out_qty
#         row["out_value"]      += out_value
#         row["bal_qty"]        += bal_qty
#         row["buy_value"]      += buy_value
#         row["sell_value"]     += sell_value
#         row["valuation_rate"]  = val_rate   # use latest
#         row["bal_val"]         = round(row["bal_qty"] * val_rate, 2)

#     # round final values
#     result = []
#     for row in items_map.values():
#         row["opening_value"] = round(row["opening_value"], 2)
#         row["in_value"]      = round(row["in_value"],      2)
#         row["out_value"]     = round(row["out_value"],     2)
#         row["buy_value"]     = round(row["buy_value"],     2)
#         row["sell_value"]    = round(row["sell_value"],    2)
#         # if no batches, set null
#         if not row["batch_no"]:
#             row["batch_no"] = None
#         result.append(row)

#     # ── Step 6: Pagination ────────────────────────────────────────────────────
#     total_records = len(result)
#     total_pages   = max(1, -(-total_records // page_size))
#     start         = (page - 1) * page_size
#     end           = start + page_size

#     return {
#         "data": result[start:end],
#         "pagination": {
#             "page":          page,
#             "page_size":     page_size,
#             "total_records": total_records,
#             "total_pages":   total_pages,
#             "has_next":      page < total_pages,
#             "has_prev":      page > 1,
#         }
#     }

@frappe.whitelist()
def get_batch_wise_stock_report(
    from_date=None,
    to_date=None,
    warehouse=None,
    item_code=None,
    item_group=None,
    batch_no=None,
    search=None,
    page=1,
    page_size=20,
):
    page      = int(page)
    page_size = int(page_size)
    company   = frappe.defaults.get_global_default("company")

    # ── Step 1: Build SQL conditions ──────────────────────────────────────────
    conditions = [
        f"company = {frappe.db.escape(company)}",
        "docstatus = 1",
        "is_cancelled = 0",
    ]
    if warehouse: conditions.append(f"warehouse = {frappe.db.escape(warehouse)}")
    if item_code: conditions.append(f"item_code = {frappe.db.escape(item_code)}")

    # Generic search across item_code, item_name, description
    if search:
        like = f"%{search}%"
        matched = frappe.db.sql("""
            SELECT item_code FROM `tabItem`
            WHERE (
                item_code   LIKE %(like)s OR
                item_name   LIKE %(like)s OR
                description LIKE %(like)s
            )
            AND disabled = 0
        """, {"like": like}, as_dict=True)

        matched_codes = [r["item_code"] for r in matched]

        if not matched_codes:
            return _empty(page, page_size)

        escaped = ", ".join(frappe.db.escape(c) for c in matched_codes)
        conditions.append(f"item_code IN ({escaped})")

    where_clause = "WHERE " + " AND ".join(conditions)

    if from_date and to_date:
        range_cond = f"AND posting_date BETWEEN {frappe.db.escape(from_date)} AND {frappe.db.escape(to_date)}"
    elif from_date:
        range_cond = f"AND posting_date >= {frappe.db.escape(from_date)}"
    elif to_date:
        range_cond = f"AND posting_date <= {frappe.db.escape(to_date)}"
    else:
        range_cond = ""

    # ── Step 2: Movement SLE grouped by item_code + warehouse ────────────────
    # NOTE: buy_value / sell_value are intentionally removed here — they were
    #       identical to in_value / out_value (both used stock_value_difference).
    #       Real sell_value (actual revenue) is fetched from Sales Invoice below.
    movement_rows = frappe.db.sql(f"""
        SELECT
            item_code,
            warehouse,
            SUM(CASE WHEN actual_qty > 0 THEN actual_qty                  ELSE 0 END) AS in_qty,
            SUM(CASE WHEN actual_qty > 0 THEN stock_value_difference      ELSE 0 END) AS in_value,
            SUM(CASE WHEN actual_qty < 0 THEN ABS(actual_qty)             ELSE 0 END) AS out_qty,
            SUM(CASE WHEN actual_qty < 0 THEN ABS(stock_value_difference) ELSE 0 END) AS out_value,
            MAX(valuation_rate)            AS last_valuation_rate,
            MAX(stock_value)               AS last_stock_value
        FROM `tabStock Ledger Entry`
        {where_clause}
        {range_cond}
        GROUP BY item_code, warehouse
    """, as_dict=True)

    if not movement_rows:
        return _empty(page, page_size)

    # ── Step 3: Opening SLE per item_code ─────────────────────────────────────
    opening_map = {}

    if from_date:
        opening_rows = frappe.db.sql(f"""
            SELECT
                sle.item_code,
                sle.warehouse,
                sle.qty_after_transaction AS opening_qty,
                sle.stock_value           AS opening_value,
                sle.valuation_rate
            FROM `tabStock Ledger Entry` sle
            INNER JOIN (
                SELECT item_code, MAX(posting_date) AS max_date
                FROM `tabStock Ledger Entry`
                {where_clause}
                  AND posting_date < {frappe.db.escape(from_date)}
                GROUP BY item_code
            ) latest
              ON  sle.item_code    = latest.item_code
              AND sle.posting_date = latest.max_date
            {where_clause}
              AND sle.posting_date < {frappe.db.escape(from_date)}
        """, as_dict=True)

        for row in opening_rows:
            opening_map[row["item_code"]] = {
                "opening_qty":    float(row["opening_qty"]    or 0),
                "opening_value":  round(float(row["opening_value"] or 0), 2),
                "valuation_rate": float(row["valuation_rate"] or 0),
            }

    # ── Step 4: Fetch item details ─────────────────────────────────────────────
    all_item_codes = list({r["item_code"] for r in movement_rows})

    item_details_map = {}
    for item in frappe.get_all(
        "Item",
        filters=[["item_code", "in", all_item_codes]],
        fields=["item_code", "item_name", "item_group", "stock_uom", "description", "name"],
        limit=0,
    ):
        item_details_map[item["item_code"]] = item
        item_metadata = frappe.db.get_value("Custom Item Details", 
                                            {"parent": item.name}, 
                                            ["*"], as_dict=True)
        item_details_map["packingUnit"] = item_metadata.packing_unit
        item_details_map["packingSize"]   = item_metadata.packing_size
    # apply item_group filter
    if item_group:
        movement_rows = [
            r for r in movement_rows
            if item_details_map.get(r["item_code"], {}).get("item_group") == item_group
        ]

    if not movement_rows:
        return _empty(page, page_size)

    # ── Step 5: Fetch REAL batch movements from Serial and Batch Bundle ───────
    escaped_codes = ", ".join(frappe.db.escape(c) for c in all_item_codes)

    # Build date filter for SBB / Sales Invoice / Purchase Invoice if date range provided
    date_cond_sbb = ""
    date_cond_si  = ""
    date_cond_pi  = ""
    if from_date and to_date:
        date_cond_sbb = f"AND sbb.posting_date BETWEEN {frappe.db.escape(from_date)} AND {frappe.db.escape(to_date)}"
        date_cond_si  = f"AND si.posting_date  BETWEEN {frappe.db.escape(from_date)} AND {frappe.db.escape(to_date)}"
        date_cond_pi  = f"AND pi.posting_date  BETWEEN {frappe.db.escape(from_date)} AND {frappe.db.escape(to_date)}"
    elif from_date:
        date_cond_sbb = f"AND sbb.posting_date >= {frappe.db.escape(from_date)}"
        date_cond_si  = f"AND si.posting_date  >= {frappe.db.escape(from_date)}"
        date_cond_pi  = f"AND pi.posting_date  >= {frappe.db.escape(from_date)}"
    elif to_date:
        date_cond_sbb = f"AND sbb.posting_date <= {frappe.db.escape(to_date)}"
        date_cond_si  = f"AND si.posting_date  <= {frappe.db.escape(to_date)}"
        date_cond_pi  = f"AND pi.posting_date  <= {frappe.db.escape(to_date)}"

    # Real inward qty per batch (cost-based — avg_rate is correct here)
    inward_rows = frappe.db.sql(f"""
        SELECT
            sbb.item_code,
            sbb.warehouse,
            sbe.batch_no,
            SUM(ABS(sbe.qty))                  AS qty,
            SUM(ABS(sbe.qty) * sbb.avg_rate)   AS value
        FROM `tabSerial and Batch Entry` sbe
        INNER JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
        WHERE sbb.item_code IN ({escaped_codes})
        AND sbb.is_cancelled = 0
        AND sbb.docstatus = 1
        AND sbb.type_of_transaction = 'Inward'
        {date_cond_sbb}
        GROUP BY sbb.item_code, sbb.warehouse, sbe.batch_no
    """, as_dict=True)

    # Real outward qty per batch (cost-based — used for out_qty/out_value only)
    outward_rows = frappe.db.sql(f"""
        SELECT
            sbb.item_code,
            sbb.warehouse,
            sbe.batch_no,
            SUM(ABS(sbe.qty))                  AS qty,
            SUM(ABS(sbe.qty) * sbb.avg_rate)   AS value
        FROM `tabSerial and Batch Entry` sbe
        INNER JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
        WHERE sbb.item_code IN ({escaped_codes})
        AND sbb.is_cancelled = 0
        AND sbb.docstatus = 1
        AND sbb.type_of_transaction = 'Outward'
        {date_cond_sbb}
        GROUP BY sbb.item_code, sbb.warehouse, sbe.batch_no
    """, as_dict=True)

    # ── FIX: Actual buy value + currency from Purchase Invoice ───────────────
    # Item-level buy  {item_code: {buy_value, buy_currency}}
    item_buy_rows = frappe.db.sql(f"""
        SELECT
            pii.item_code,
            pi.currency,
            SUM(pii.amount) AS buy_value
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.item_code IN ({escaped_codes})
        AND pi.docstatus = 1
        AND pi.company   = {frappe.db.escape(company)}
        {date_cond_pi}
        GROUP BY pii.item_code, pi.currency
    """, as_dict=True)

    item_buy_map = {}
    for r in item_buy_rows:
        item_buy_map[r["item_code"]] = {
            "buy_value":    round(float(r["buy_value"] or 0), 2),
            "buy_currency": r["currency"] or "INR",
        }

    # Batch-level buy  {(item_code, batch_no): {buy_value, buy_currency}}
    batch_buy_rows = frappe.db.sql(f"""
        SELECT
            pii.item_code,
            pii.batch_no,
            pi.currency,
            SUM(pii.amount) AS buy_value
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
        WHERE pii.item_code IN ({escaped_codes})
        AND pi.docstatus = 1
        AND pi.company   = {frappe.db.escape(company)}
        {date_cond_pi}
        GROUP BY pii.item_code, pii.batch_no, pi.currency
    """, as_dict=True)

    batch_buy_map = {}
    for r in batch_buy_rows:
        key = (r["item_code"], r["batch_no"])
        batch_buy_map[key] = {
            "buy_value":    round(float(r["buy_value"] or 0), 2),
            "buy_currency": r["currency"] or "INR",
        }

    # ── Actual sell value + currency from Sales Invoice ───────────────────────
    # Item-level sell  {item_code: {sell_value, sell_currency}}
    item_sell_rows = frappe.db.sql(f"""
        SELECT
            sii.item_code,
            si.currency,
            SUM(sii.amount) AS sell_value
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.item_code IN ({escaped_codes})
        AND si.docstatus = 1
        AND si.company   = {frappe.db.escape(company)}
        {date_cond_si}
        GROUP BY sii.item_code, si.currency
    """, as_dict=True)

    item_sell_map = {}
    for r in item_sell_rows:
        item_sell_map[r["item_code"]] = {
            "sell_value":    round(float(r["sell_value"] or 0), 2),
            "sell_currency": r["currency"] or "INR",
        }

    # Batch-level sell  {(item_code, batch_no): {sell_value, sell_currency}}
    batch_sell_rows = frappe.db.sql(f"""
        SELECT
            sii.item_code,
            sii.batch_no,
            si.currency,
            SUM(sii.amount) AS sell_value
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.item_code IN ({escaped_codes})
        AND si.docstatus = 1
        AND si.company   = {frappe.db.escape(company)}
        {date_cond_si}
        GROUP BY sii.item_code, sii.batch_no, si.currency
    """, as_dict=True)

    batch_sell_map = {}
    for r in batch_sell_rows:
        key = (r["item_code"], r["batch_no"])
        batch_sell_map[key] = {
            "sell_value":    round(float(r["sell_value"] or 0), 2),
            "sell_currency": r["currency"] or "INR",
        }

    # Build lookup maps  {(item_code, warehouse, batch_no): {qty, value}}
    inward_map  = {}
    outward_map = {}

    for r in inward_rows:
        key = (r["item_code"], r["warehouse"], r["batch_no"])
        inward_map[key] = {"qty": float(r["qty"] or 0), "value": round(float(r["value"] or 0), 2)}

    for r in outward_rows:
        key = (r["item_code"], r["warehouse"], r["batch_no"])
        outward_map[key] = {"qty": float(r["qty"] or 0), "value": round(float(r["value"] or 0), 2)}

    # Collect all batch_nos that actually have movements
    all_active_batch_nos = set(
        [k[2] for k in inward_map.keys()] + [k[2] for k in outward_map.keys()]
    )

    # Fetch batch metadata (expiry, manufacturing date) from tabBatch
    batch_meta_map = {}
    batch_meta_filters = [["item", "in", all_item_codes], ["disabled", "=", 0]]
    if batch_no:
        batch_meta_filters.append(["name", "=", batch_no])

    for b in frappe.get_all(
        "Batch",
        filters=batch_meta_filters,
        fields=["name as batch_no", "item as item_code", "expiry_date", "manufacturing_date"],
        limit=0,
    ):
        batch_meta_map[b["batch_no"]] = b

    # Group active batches by item_code
    batches_by_item = {}
    for b_no in all_active_batch_nos:
        meta = batch_meta_map.get(b_no, {})
        i_code = meta.get("item_code")
        if not i_code:
            # Try to find item_code from inward/outward maps
            for key in list(inward_map.keys()) + list(outward_map.keys()):
                if key[2] == b_no:
                    i_code = key[0]
                    break
        if i_code:
            batches_by_item.setdefault(i_code, []).append({
                "batch_no":           b_no,
                "expiry_date":        meta.get("expiry_date"),
                "manufacturing_date": meta.get("manufacturing_date"),
                "item_code":          i_code,
            })

    # ── Step 6: Build result ───────────────────────────────────────────────────
    items_map = {}

    for row in movement_rows:
        code = row["item_code"]
        wh   = row["warehouse"]

        item_info = item_details_map.get(code, {
            "item_name": "", "item_group": "", "stock_uom": "", "description": "", "packing_size": "", "packing_unit": ""
        })
        o = opening_map.get(code, {
            "opening_qty":    0.0,
            "opening_value":  0.0,
            "valuation_rate": 0.0,
        })

        opening_qty   = o["opening_qty"]
        opening_value = o["opening_value"]
        in_qty        = float(row["in_qty"]    or 0)
        in_value      = round(float(row["in_value"]   or 0), 2)
        out_qty       = float(row["out_qty"]   or 0)
        out_value     = round(float(row["out_value"]  or 0), 2)
        bal_qty       = opening_qty + in_qty - out_qty
        val_rate      = float(row["last_valuation_rate"] or 0) or o["valuation_rate"]
        bal_val       = round(bal_qty * val_rate, 2)

        # buy_value/currency  = from Purchase Invoice (actual cost + currency)
        # sell_value/currency = from Sales Invoice   (actual revenue + currency)
        buy_info  = item_buy_map.get(code,  {"buy_value":  in_value, "buy_currency":  "INR"})
        sell_info = item_sell_map.get(code, {"sell_value": 0.0,      "sell_currency": "INR"})

        buy_value     = buy_info["buy_value"]
        buy_currency  = buy_info["buy_currency"]
        sell_value    = sell_info["sell_value"]
        sell_currency = sell_info["sell_currency"]

        item_batches = batches_by_item.get(code, [])
        batch_rows   = []

        for b in item_batches:
            b_no     = b["batch_no"]
            in_key   = (code, wh, b_no)
            out_key  = (code, wh, b_no)

            b_in_qty    = inward_map.get(in_key,   {}).get("qty",   0.0)
            b_in_value  = inward_map.get(in_key,   {}).get("value", 0.0)
            b_out_qty   = outward_map.get(out_key, {}).get("qty",   0.0)
            b_out_value = outward_map.get(out_key, {}).get("value", 0.0)
            b_bal_qty   = b_in_qty - b_out_qty

            # Skip batches with no real activity
            if b_in_qty == 0 and b_out_qty == 0:
                continue

            # Batch buy/sell value with currency
            b_buy_info   = batch_buy_map.get((code, b_no),  {"buy_value":  round(b_in_value, 2), "buy_currency":  buy_currency})
            b_sell_info  = batch_sell_map.get((code, b_no), {"sell_value": 0.0,                  "sell_currency": sell_currency})

            batch_rows.append({
                "batch_no":           b_no,
                "expiry_date":        b.get("expiry_date"),
                "manufacturing_date": b.get("manufacturing_date"),
                "warehouse":          wh,
                "opening_qty":        round(opening_qty, 4),
                "opening_value":      opening_value,
                "in_qty":             round(b_in_qty,    4),
                "in_value":           round(b_in_value,  2),
                "out_qty":            round(b_out_qty,   4),
                "out_value":          round(b_out_value, 2),
                "bal_qty":            round(b_bal_qty,   4),
                "bal_val":            round(b_bal_qty * val_rate, 2),
                "valuation_rate":     val_rate,
                "buy_value":          b_buy_info["buy_value"],
                "buy_currency":       b_buy_info["buy_currency"],
                "sell_value":         b_sell_info["sell_value"],
                "sell_currency":      b_sell_info["sell_currency"],
            })

        # Fallback: no batch tracking
        if not batch_rows:
            batch_rows.append({
                "batch_no":           None,
                "expiry_date":        None,
                "manufacturing_date": None,
                "warehouse":          wh,
                "opening_qty":        opening_qty,
                "opening_value":      opening_value,
                "in_qty":             in_qty,
                "in_value":           in_value,
                "out_qty":            out_qty,
                "out_value":          out_value,
                "bal_qty":            bal_qty,
                "bal_val":            bal_val,
                "valuation_rate":     val_rate,
                "buy_value":          buy_value,
                "buy_currency":       buy_currency,
                "sell_value":         sell_value,
                "sell_currency":      sell_currency,
            })

        if code not in items_map:
            items_map[code] = {
                "item_code":           code,
                "item_name":           item_info.get("item_name",   ""),
                "item_group":          item_info.get("item_group",  ""),
                "stock_uom":           item_info.get("stock_uom",   ""),
                "description":         item_info.get("description", ""),
                "packingSize":         item_info.get("packing_size",""),
                "packingUnit":         item_info.get("packing_unit",""),
                "total_opening_qty":   round(opening_qty,   4),
                "total_opening_value": opening_value,
                "total_in_qty":        in_qty,
                "total_in_value":      in_value,
                "total_out_qty":       out_qty,
                "total_out_value":     out_value,
                "total_bal_qty":       bal_qty,
                "total_bal_val":       bal_val,
                "total_buy_value":     buy_value,
                "buy_currency":        buy_currency,
                "total_sell_value":    sell_value,
                "sell_currency":       sell_currency,
                "batches":             batch_rows,
            }

    # ── Step 7: Pagination ────────────────────────────────────────────────────
    result        = list(items_map.values())
    total_records = len(result)
    total_pages   = max(1, -(-total_records // page_size))
    start         = (page - 1) * page_size
    end           = start + page_size

    return {
        "data": result[start:end],
        "pagination": {
            "page":          page,
            "page_size":     page_size,
            "total_records": total_records,
            "total_pages":   total_pages,
            "has_next":      page < total_pages,
            "has_prev":      page > 1,
        }
    }


def _empty(page, page_size):
    return {
        "data": [],
        "pagination": {
            "page": page, "page_size": page_size,
            "total_records": 0, "total_pages": 0,
            "has_next": False, "has_prev": False,
        }
    }