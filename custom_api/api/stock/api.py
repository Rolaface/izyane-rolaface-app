from custom_api.api.item.utils.item_utils import _get_tax
import frappe

from custom_api.utils.response import send_response

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
    params    = frappe.request.args
    tax_category = params.get("taxCategory")

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
        item_details_map[item["item_code"]]["packing_unit"] = item_metadata.packing_unit
        item_details_map[item["item_code"]]["packing_size"] = item_metadata.packing_size
        item_details_map[item["item_code"]]["taxInfo"] = _get_tax(item.name, tax_category)

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
            "item_name": "", "item_group": "", "stock_uom": "", "description": "", "packing_size": "", "packing_unit": "",
            "taxInfo": ""
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
                "taxInfo":             item_info.get("taxInfo", ""),
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
    # ── Step 6b: Append non-stock items (maintain_stock=0, for sale) ─────────
    non_stock_items = frappe.get_all(
        "Item",
        filters={
            "is_stock_item":  0,
            "is_sales_item":  1,
            "disabled":       0,
        },
        fields=["item_code", "item_name", "item_group", "stock_uom", "description", "name"],
        limit=0,
    )

    for item in non_stock_items:
        code = item["item_code"]

        # ── Skip if already present from movement rows ────────────────────────
        if code in items_map:
            continue

        # ── Fetch custom metadata (packing info + tax) ────────────────────────
        item_metadata = frappe.db.get_value(
            "Custom Item Details",
            {"parent": item.name},
            ["*"],
            as_dict=True,
        )

        packing_size = item_metadata.packing_size if item_metadata else ""
        packing_unit = item_metadata.packing_unit if item_metadata else ""
        tax_info     = _get_tax(item.name, tax_category)

        # ── Buy/sell values from invoices ─────────────────────────────────────
        buy_info  = item_buy_map.get(code,  {"buy_value": 0.0, "buy_currency":  "INR"})
        sell_info = item_sell_map.get(code, {"sell_value": 0.0, "sell_currency": "INR"})

        items_map[code] = {
            "item_code":           code,
            "item_name":           item["item_name"]  or "",
            "item_group":          item["item_group"] or "",
            "stock_uom":           item["stock_uom"]  or "",
            "description":         item["description"] or "",
            "packingSize":         packing_size,
            "packingUnit":         packing_unit,
            "taxInfo":             tax_info,
            "total_opening_qty":   0.0,
            "total_opening_value": 0.0,
            "total_in_qty":        0.0,
            "total_in_value":      0.0,
            "total_out_qty":       0.0,
            "total_out_value":     0.0,
            "total_bal_qty":       0.0,
            "total_bal_val":       0.0,
            "total_buy_value":     buy_info["buy_value"],
            "buy_currency":        buy_info["buy_currency"],
            "total_sell_value":    sell_info["sell_value"],
            "sell_currency":       sell_info["sell_currency"],
            "batches":             [],
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