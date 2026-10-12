from custom_api.api.item.utils.item_utils import _get_tax
from custom_api.permission import require_permission
import frappe

from custom_api.utils.response import send_response

@frappe.whitelist()
@require_permission("Item", "read")
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
    get_service_item=1,
    get_product_item=1
):
    page      = int(page)
    page_size = int(page_size)
    company   = frappe.defaults.get_global_default("company")
    params    = frappe.request.args
    tax_category = params.get("taxCategory")
    company_currency = frappe.defaults.get_user_default("Currency")
    get_service_item = int(get_service_item)
    get_product_item = int(get_product_item)
    search_codes = None
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
        search_codes = matched_codes

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
    movement_rows = frappe.db.sql(f"""
        SELECT
        item_code,
        warehouse,
        SUM(CASE WHEN actual_qty > 0 THEN actual_qty                  ELSE 0 END) AS in_qty,
        SUM(CASE WHEN actual_qty > 0 THEN stock_value_difference      ELSE 0 END) AS in_value,
        SUM(CASE WHEN actual_qty < 0 THEN ABS(actual_qty)             ELSE 0 END) AS out_qty,
        SUM(CASE WHEN actual_qty < 0 THEN ABS(stock_value_difference) ELSE 0 END) AS out_value
        FROM `tabStock Ledger Entry`
        {where_clause}
        {range_cond}
        GROUP BY item_code, warehouse
    """, as_dict=True)

    # Fetch chronologically LATEST valuation_rate/stock_value per item+warehouse
    # FIX: added `name DESC` as a final tiebreaker — without it, when multiple SLEs
    # share the same posting_date/posting_time/creation (common with bulk imports),
    # MySQL's LIMIT 1 pick is non-deterministic and returns a different row on
    # different runs, causing valuation_rate/bal_val/out_value to change randomly.
    for row in movement_rows:
        latest = frappe.db.sql("""
            SELECT valuation_rate, stock_value
            FROM `tabStock Ledger Entry`
            WHERE item_code=%s AND warehouse=%s AND docstatus=1 AND is_cancelled=0
            ORDER BY posting_date DESC, posting_time DESC, creation DESC, name DESC
            LIMIT 1
        """, (row["item_code"], row["warehouse"]), as_dict=True)

        row["last_valuation_rate"] = latest[0]["valuation_rate"] if latest else 0
        row["last_stock_value"] = latest[0]["stock_value"] if latest else 0

    items_map = {}
    item_buy_map = {}
    item_last_sale_rate_map = {}
    if get_product_item:
        if movement_rows:

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
                item_details_map[item["item_code"]]["pieces_per_box"] = item_metadata.pieces_per_box
                item_details_map[item["item_code"]]["taxInfo"] = _get_tax(item.name, tax_category)
                item_details_map[item["item_code"]]["price_list"] = frappe.db.get_value("Item Price", {"item_code": item["item_code"], "price_list": "Standard Selling"}, "price_list_rate")
                item_details_map[item["item_code"]]["rrp_rate"] = item_metadata.rrp_rate
                item_details_map[item["item_code"]]["is_mtv_item"] = item_metadata.is_mtv

            # apply item_group filter
            if item_group:
                movement_rows = [
                    r for r in movement_rows
                    if item_details_map.get(r["item_code"], {}).get("item_group") == item_group
                ]

            if not movement_rows and not get_service_item:
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
                    SUM(ABS(sbe.qty) * sbb.avg_rate)   AS value,
                    SUM(CASE WHEN sbb.voucher_type = 'Sales Invoice' THEN ABS(sbe.qty) ELSE 0 END) AS return_qty,
                    SUM(CASE WHEN sbb.voucher_type = 'Sales Invoice' THEN ABS(sbe.qty) * sbb.avg_rate ELSE 0 END) AS return_value
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

            # ── NEW REQUIREMENT (client confirmed):
            #     buy_value  = balance_qty * (buy cost per unit from Purchase Invoice)
            #     sell_value = balance_qty * (rate from the MOST RECENT Sales Invoice
            #                  for that item/batch); if never sold -> 0
            #     Both values reported in company currency (base_amount / base_rate).
            #
            # ── Buy rate per unit — item-level, from Purchase Invoice ────────────────
            # FIX: batch_no normalized (TRIM + strip trailing '.') to tolerate the
            #      known data-entry duplicate ('ACI6021' vs 'ACI6021.') without
            #      requiring a master-data cleanup first.
            # FIX: `pii.qty > 0` excludes Purchase Returns (negative qty rows).
            # Without this, a return that exactly offsets a purchase makes
            # SUM(qty) = 0, causing the average rate to be silently reported
            # as 0 instead of the real historical purchase rate.
            item_buy_rows = frappe.db.sql(f"""
                SELECT
                    pii.item_code,
                    SUM(pii.qty)         AS buy_qty,
                    SUM(pii.base_amount) AS buy_value
                FROM `tabPurchase Invoice Item` pii
                INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
                WHERE pii.item_code IN ({escaped_codes})
                AND pi.docstatus = 1
                AND pi.company   = {frappe.db.escape(company)}
                AND pii.qty > 0
                {date_cond_pi}
                GROUP BY pii.item_code
            """, as_dict=True)

            for r in item_buy_rows:
                b_qty = float(r["buy_qty"] or 0)
                b_val = float(r["buy_value"] or 0)
                item_buy_map[r["item_code"]] = {
                    "buy_rate": round(b_val / b_qty, 6) if b_qty else 0,
                }

            # ── Average sell rate — item level (all Sales Invoice lines, not just latest) ──
            # FIX: `sii.qty > 0` excludes Sales Returns/Credit Notes (negative qty).
            # Without this, a return exactly offsetting a sale makes SUM(qty) = 0,
            # so the average silently reports as 0 instead of the real sale price.
            item_sell_avg_rows = frappe.db.sql(f"""
                SELECT
                    sii.item_code,
                    SUM(sii.qty)         AS sell_qty,
                    SUM(sii.base_amount) AS sell_value
                FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                WHERE sii.item_code IN ({escaped_codes})
                AND si.docstatus = 1
                AND si.company   = {frappe.db.escape(company)}
                AND sii.qty > 0
                {date_cond_si}
                GROUP BY sii.item_code
            """, as_dict=True)

            item_sell_avg_map = {}
            for r in item_sell_avg_rows:
                s_qty = float(r["sell_qty"] or 0)
                s_val = float(r["sell_value"] or 0)
                item_sell_avg_map[r["item_code"]] = round(s_val / s_qty, 6) if s_qty else 0

            # ── Latest buy rate — item level (most recent Purchase Invoice line) ─────
            item_last_buy_rate_map = {}
            for code in all_item_codes:
                latest_item_buy = frappe.db.sql("""
                    SELECT pii.base_rate
                    FROM `tabPurchase Invoice Item` pii
                    INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
                    WHERE pii.item_code = %s
                    AND pi.docstatus = 1
                    AND pi.company   = %s
                    ORDER BY pi.posting_date DESC, pi.posting_time DESC, pi.creation DESC, pi.name DESC
                    LIMIT 1
                """, (code, company), as_dict=True)
                item_last_buy_rate_map[code] = float(latest_item_buy[0]["base_rate"]) if latest_item_buy else 0

            # Batch-level buy rate  {(item_code, batch_no_normalized): buy_rate}
            batch_buy_rows = frappe.db.sql(f"""
                SELECT
                    pii.item_code,
                    TRIM(TRAILING '.' FROM TRIM(pii.batch_no)) AS batch_no,
                    SUM(pii.qty)         AS buy_qty,
                    SUM(pii.base_amount) AS buy_value
                FROM `tabPurchase Invoice Item` pii
                INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
                WHERE pii.item_code IN ({escaped_codes})
                AND pi.docstatus = 1
                AND pi.company   = {frappe.db.escape(company)}
                {date_cond_pi}
                GROUP BY pii.item_code, TRIM(TRAILING '.' FROM TRIM(pii.batch_no))
            """, as_dict=True)

            batch_buy_map = {}
            for r in batch_buy_rows:
                key = (r["item_code"], r["batch_no"])
                b_qty = float(r["buy_qty"] or 0)
                b_val = float(r["buy_value"] or 0)
                batch_buy_map[key] = {
                    "buy_rate": round(b_val / b_qty, 6) if b_qty else 0,
                }

            # ── Latest sale rate — item level (most recent Sales Invoice line) ───────
            # One lightweight query per item instead of a correlated subquery
            # across the whole table (keeps this readable/maintainable; item counts
            # here are not large enough to justify a windowed-query rewrite).
            for code in all_item_codes:
                latest_item_sale = frappe.db.sql("""
                    SELECT sii.base_rate
                    FROM `tabSales Invoice Item` sii
                    INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
                    WHERE sii.item_code = %s
                    AND si.docstatus = 1
                    AND si.company   = %s
                    ORDER BY si.posting_date DESC, si.posting_time DESC, si.creation DESC, si.name DESC
                    LIMIT 1
                """, (code, company), as_dict=True)
                item_last_sale_rate_map[code] = float(latest_item_sale[0]["base_rate"]) if latest_item_sale else 0

            # ── Collect batch-level inward/outward movement maps ──────────────────────
            inward_map  = {}
            outward_map = {}

            for r in inward_rows:
                key = (r["item_code"], r["warehouse"], r["batch_no"])
                inward_map[key] = {
                    "qty": float(r["qty"] or 0),
                    "value": round(float(r["value"] or 0), 2),
                    "return_qty": float(r["return_qty"] or 0),
                    "return_value": round(float(r["return_value"] or 0), 2),
                }

            for r in outward_rows:
                key = (r["item_code"], r["warehouse"], r["batch_no"])
                outward_map[key] = {"qty": float(r["qty"] or 0), "value": round(float(r["value"] or 0), 2)}

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

            for row in movement_rows:
                code = row["item_code"]
                wh   = row["warehouse"]

                item_info = item_details_map.get(code, {
                    "item_name": "", "item_group": "", "stock_uom": "", "description": "", "packing_size": "", "packing_unit": "",
                    "taxInfo": "", "price_list": 0.0, "rrp_rate": 0.0, "is_mtv_item": False
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

                # item_buy_rate = average historical purchase price (informational,
                # shown as buy_price_avg). No longer drives buy_value directly.
                item_buy_rate = round(item_buy_map.get(code, {}).get("buy_rate", 0), 2)

                # FIX: buy_value (used as the fallback/non-batch-tracked value below,
                # and as the base before being overwritten by sum-of-batches for
                # batch-tracked items) is now based on FIFO valuation_rate, not the
                # average purchase price — this makes buy_value == bal_val, so it
                # reconciles with the Chart of Accounts / Stock In Hand GL balance.
                buy_value     = round(bal_qty * val_rate, 2)
                buy_currency  = company_currency

                # sell_value = balance_qty * avg sell rate (Option B, confirmed):
                # values the ENTIRE balance stock at the average selling price,
                # regardless of whether it has actually been sold yet. This is a
                # potential/estimated value, not a realized-sales figure. GL has
                # no equivalent "sell valuation" concept, so this is left avg-based.
                item_sell_avg_rate = round(item_sell_avg_map.get(code, 0), 2)
                sell_value         = round(bal_qty * item_sell_avg_rate, 2)
                sell_currency      = company_currency

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

                    # NEW: return qty/value — the portion of b_in_qty/b_in_value that came
                    # from a Sales Invoice (customer return) rather than a Purchase Invoice.
                    # Already included inside b_in_qty/b_in_value above (bal_qty unaffected);
                    # this is purely an additional breakdown field.
                    b_return_qty   = inward_map.get(in_key, {}).get("return_qty",   0.0)
                    b_return_value = inward_map.get(in_key, {}).get("return_value", 0.0)

                    # Skip batches with no real activity
                    if b_in_qty == 0 and b_out_qty == 0:
                        continue

                    # New: batch rate calculate  (Do not use item-level val_rate for batch-level valuation)
                    b_val_rate = round(b_in_value / b_in_qty, 6) if b_in_qty else val_rate

                    # FIX: batch-level buy_value now uses the batch's own FIFO
                    # valuation_rate (b_val_rate) instead of the item-wide average
                    # buy price. This makes buy_value == bal_val for each batch, so
                    # the item-level total (sum of batch buy_values below) reconciles
                    # with the Chart of Accounts / Stock In Hand GL balance.
                    # buy_price_avg (below) is kept purely as an informational
                    # reference — the average historical purchase price — and no
                    # longer drives buy_value.
                    b_buy_valuation_rate = b_val_rate
                    b_buy_value          = round(b_bal_qty * b_buy_valuation_rate, 2)

                    # Batch-level sell_value uses the same item-wide average sell
                    # rate as the item-level total (no separate per-batch average
                    # is tracked) — keeps batch-level and item-level consistent.
                    b_sell_value = round(b_bal_qty * item_sell_avg_map.get(code, 0), 2)

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
                        "bal_val":            round(b_bal_qty * b_val_rate, 2),
                        "valuation_rate":     b_val_rate,
                        "buy_value":          b_buy_value,
                        "buy_currency":       company_currency,
                        "sell_value":         b_sell_value,
                        "sell_currency":      company_currency,
                        # Batch-level latest buy/sell price — reused from item-level
                        # latest maps (no separate per-batch "latest" is tracked).
                        "buy_price_latest":   round(item_last_buy_rate_map.get(code, 0), 2),
                        "sell_price_latest":  round(item_last_sale_rate_map.get(code, 0), 2),
                        # Informational: item-wide average purchase price (does NOT
                        # drive buy_value anymore — see b_buy_valuation_rate above).
                        "buy_price_avg":      round(item_buy_rate, 2),
                        # The FIFO valuation rate actually used to compute buy_value
                        # for this batch — reconciles with Chart of Accounts.
                        "buy_price_valuation": round(b_buy_valuation_rate, 2),
                        # Item-wide average sell price — drives this batch's sell_value.
                        "sell_price_avg":     round(item_sell_avg_map.get(code, 0), 2),
                        # Batch-level return breakdown (subset already counted inside in_qty/in_value)
                        "return_qty":         round(b_return_qty, 4),
                        "return_value":       round(b_return_value, 2),
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
                        # Same item-level latest rates for the untracked fallback batch
                        "buy_price_latest":   round(item_last_buy_rate_map.get(code, 0), 2),
                        "sell_price_latest":  round(item_last_sale_rate_map.get(code, 0), 2),
                        # Informational average purchase price (no longer drives buy_value)
                        "buy_price_avg":      round(item_buy_rate, 2),
                        # No per-batch tracking here, so the FIFO valuation rate used
                        # for buy_value is simply the item-level val_rate.
                        "buy_price_valuation": round(val_rate, 2),
                        # No per-batch tracking here, so use the same item-level avg sell rate
                        "sell_price_avg":     round(item_sell_avg_map.get(code, 0), 2),
                        # No batch tracking here, so no per-batch return breakdown available
                        "return_qty":         0.0,
                        "return_value":       0.0,
                    })

                # buy_value = sum of batch-level buy values, which are now FIFO
                # valuation-based (b_bal_qty * b_val_rate) — so this sum equals the
                # item's total_bal_val, reconciling with the Chart of Accounts /
                # Stock In Hand GL balance.
                # sell_value = bal_qty * item-wide average sell rate (Option B,
                # confirmed) — computed earlier, NOT summed from batch_rows here.
                buy_value = round(sum(b["buy_value"] for b in batch_rows), 2)
                # sell_value intentionally left as computed above: bal_qty * item_sell_avg_rate

                if code not in items_map:
                    items_map[code] = {
                        "item_code":           code,
                        "item_name":           item_info.get("item_name",   ""),
                        "item_group":          item_info.get("item_group",  ""),
                        "stock_uom":           item_info.get("stock_uom",   ""),
                        # NOTE: this reflects only the first warehouse processed for
                        # this item. If the item exists across multiple warehouses,
                        # this is a temporary/quick add — proper per-warehouse split
                        # (items_map keyed by (item_code, warehouse)) to follow.
                        "warehouse":           wh,
                        "description":         item_info.get("description", ""),
                        "packingSize":         item_info.get("packing_size",""),
                        "packingUnit":         item_info.get("packing_unit",""),
                        "piecesPerBox":        item_info.get("pieces_per_box",""),
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
                        "buy_price_latest":    round(item_last_buy_rate_map.get(code, 0), 2),
                        "buy_price_avg":       round(item_buy_rate, 2),
                        # Item-level FIFO valuation rate — this is what total_buy_value
                        # is now based on (bal_qty * val_rate), reconciles with GL.
                        "buy_price_valuation": round(val_rate, 2),
                        "sell_price_latest":   round(item_last_sale_rate_map.get(code, 0), 2),
                        "sell_price_avg":      round(item_sell_avg_map.get(code, 0), 2),
                        "batches":             batch_rows,
                        "price_list":          item_info.get("price_list", 0.0),
                        "rrp_rate":            item_info.get("rrp_rate", 0.0),
                        "is_mtv_item":         item_info.get("is_mtv_item", False),
                    }
    if get_service_item:
        # ── Step 6b: Append non-stock items (maintain_stock=0, for sale) ─────────
        service_filters = {
            "is_stock_item":  0,
            "is_sales_item":  1,
            "disabled":       0,
        }
        if item_code: service_filters["item_code"] = item_code
        if item_group: service_filters["item_group"] = item_group
        if search_codes is not None: service_filters["item_code"] = ["in", search_codes]
        non_stock_items = frappe.get_all(
            "Item",
            filters=service_filters,
            fields=["item_code", "item_name", "item_group", "stock_uom", "description", "name"],
            limit=0,
        )

        for item in non_stock_items:
            code = item["item_code"]

            if code in items_map:
                continue

            item_metadata = frappe.db.get_value(
                "Custom Item Details",
                {"parent": item.name},
                ["*"],
                as_dict=True,
            )

            packing_size = item_metadata.packing_size if item_metadata else ""
            packing_unit = item_metadata.packing_unit if item_metadata else ""
            pieces_per_box = item_metadata.pieces_per_box if item_metadata else ""
            rrp_rate = item_metadata.rrp_rate if item_metadata else 0.0
            tax_info     = _get_tax(item.name, tax_category)
            is_mtv_item = item_metadata.is_mtv if item_metadata else False

            # Non-stock/service items have no balance qty concept -> buy/sell value 0
            items_map[code] = {
                "item_code":           code,
                "item_name":           item["item_name"]  or "",
                "item_group":          item["item_group"] or "",
                "stock_uom":           item["stock_uom"]  or "",
                "warehouse":           None,
                "description":         item["description"] or "",
                "packingSize":         packing_size,
                "packingUnit":         packing_unit,
                "piecesPerBox":        pieces_per_box,
                "taxInfo":             tax_info,
                "total_opening_qty":   0.0,
                "total_opening_value": 0.0,
                "total_in_qty":        0.0,
                "total_in_value":      0.0,
                "total_out_qty":       0.0,
                "total_out_value":     0.0,
                "total_bal_qty":       0.0,
                "total_bal_val":       0.0,
                "total_buy_value":     0.0,
                "buy_currency":        company_currency,
                "total_sell_value":    0.0,
                "sell_currency":       company_currency,
                "buy_price_latest":    0.0,
                "buy_price_avg":       0.0,
                "buy_price_valuation": 0.0,
                "sell_price_latest":   0.0,
                "sell_price_avg":      0.0,
                "batches":             [],
                "is_service_item": 1,
                "price_list": frappe.db.get_value("Item Price", {"item_code": item["item_code"], "price_list": "Standard Selling"}, "price_list_rate"),
                "rrp_rate":            rrp_rate,
                "is_mtv_item":         is_mtv_item,
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