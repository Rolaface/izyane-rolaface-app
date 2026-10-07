import frappe
from datetime import timedelta
from frappe.utils import flt, cint, getdate, nowdate, date_diff, get_datetime


def get_sales_dashboard_data(year=None, order_by=None):
    company = frappe.defaults.get_user_default("Company") or frappe.get_default("Company")
    year = cint(year) or getdate(nowdate()).year
    currency = frappe.db.get_value("Company", company, "default_currency")
    monthly_overview = get_monthly_sales_overview(company, year)

    return {
        "currency": currency,
        "period": {"year": year, "granularity": "monthly"},
        "summary": get_document_counts(company),
        "monthly_sales_overview": monthly_overview,
        "monthly_sales_year_total": get_monthly_year_total(monthly_overview), 
        "quotation_conversion": get_quotation_conversion(company, year),
        "customer_concentration": get_customer_concentration(company, year),
        "needs_attention": get_needs_attention(company),
        "action_items": get_action_items(company),
        "top_recent_sales": get_top_recent_sales(company, order_by),
        "invoice_status": get_invoice_status_breakdown(company, year),
        "overdue_invoice_aging": get_overdue_invoice_aging(company),
        "recent_sales_activity": get_recent_sales_activity(company),
    }


def get_quotation_extended_count_and_value(company, document_type):
    row = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT q.name) AS count, COALESCE(SUM(q.base_grand_total), 0) AS value
        FROM `tabQuotation` q
        INNER JOIN `tabCustom Quotation Extended Details` c
            ON c.parent = q.name
        WHERE
            q.docstatus = 1
            AND q.company = %(company)s
            AND c.document_type = %(document_type)s
        """,
        {"company": company, "document_type": document_type},
        as_dict=True,
    )[0]
    return {"count": cint(row.count), "value": flt(row.value)}


def _count_and_value(doctype, filters):
    row = frappe.db.sql(
        f"""
        SELECT COUNT(*) AS count, COALESCE(SUM(base_grand_total), 0) AS value
        FROM `tab{doctype}`
        WHERE docstatus = %(docstatus)s AND company = %(company)s
            AND is_return = %(is_return)s
        """,
        filters,
        as_dict=True,
    )[0]
    return {"count": cint(row.count), "value": flt(row.value)}


def get_document_counts(company):
    base_filters = {"docstatus": 1, "company": company}

    return {
        "proforma_invoices": get_quotation_extended_count_and_value(company, "Proforma Invoice"),
        "quotations": get_quotation_extended_count_and_value(company, "Quotation"),
        "sales_orders": {
            "count": frappe.db.count("Sales Order", filters=base_filters),
            "value": flt(frappe.db.sql(
                """SELECT COALESCE(SUM(base_grand_total), 0) FROM `tabSales Order`
                   WHERE docstatus = 1 AND company = %(company)s""",
                {"company": company},
            )[0][0]),
        },
        "sales_invoices": _count_and_value("Sales Invoice", {**base_filters, "is_return": 0}),
        "credit_notes": _count_and_value("Sales Invoice", {**base_filters, "is_return": 1}),
        "debit_notes": _count_and_value("Purchase Invoice", {**base_filters, "is_return": 1}),
    }

def get_monthly_sales_overview(company, year):
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    data = [{"month": m, "received": 0.0, "receivable": 0.0} for m in months]

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "company": company,
            "posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
        },
        fields=["posting_date", "base_grand_total", "outstanding_amount", "conversion_rate"],
    )

    for inv in invoices:
        month_idx = getdate(inv.posting_date).month - 1
        conv_rate = flt(inv.conversion_rate) or 1.0
        receivable = flt(inv.outstanding_amount) * conv_rate
        received = flt(inv.base_grand_total) - receivable

        data[month_idx]["received"] += received
        data[month_idx]["receivable"] += receivable

    for row in data:
        row["total"] = row["received"] + row["receivable"]

    return data


def get_quotation_conversion(company, year):
    row = frappe.db.sql(
        """
        SELECT
            COUNT(DISTINCT q.name) AS total,
            COUNT(DISTINCT CASE WHEN q.status = 'Ordered' THEN q.name END) AS converted
        FROM `tabQuotation` q
        INNER JOIN `tabCustom Quotation Extended Details` c
            ON c.parent = q.name
        WHERE
            q.docstatus = 1
            AND q.company = %(company)s
            AND c.document_type = 'Quotation'
            AND q.transaction_date BETWEEN %(start)s AND %(end)s
        """,
        {"company": company, "start": f"{year}-01-01", "end": f"{year}-12-31"},
        as_dict=True,
    )[0]

    total = cint(row.total)
    converted = cint(row.converted)

    return {
        "total_quotations": total,
        "converted_quotations": converted,
        "conversion_rate_percent": round((converted / total) * 100) if total else 0,
    }

def get_monthly_year_total(monthly_data):
    received = sum(r["received"] for r in monthly_data)
    receivable = sum(r["receivable"] for r in monthly_data)
    return {
        "received": received,
        "receivable": receivable,
        "total": received + receivable,
    }

def get_customer_concentration(company, year):
    rows = frappe.db.sql(
        """
        SELECT customer AS customer_id, customer_name, SUM(base_grand_total) AS revenue
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
            AND posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY customer
        ORDER BY revenue DESC
        """,
        {"company": company, "start": f"{year}-01-01", "end": f"{year}-12-31"},
        as_dict=True,
    )

    total_revenue = sum(flt(r.revenue) for r in rows)

    if not rows or not total_revenue:
        return {"top_customer_name": None, "top_customer_revenue_percent": 0, "total_tracked_revenue": 0.0}

    top = rows[0]

    return {
        "top_customer_name": top.customer_name,
        "top_customer_revenue_percent": round((flt(top.revenue) / total_revenue) * 100),
        "total_tracked_revenue": total_revenue,
    }


def get_needs_attention(company, inactive_days=60, limit=10):
    rows = frappe.db.sql(
        """
        SELECT customer AS customer_id, customer_name, MAX(posting_date) AS last_order_date
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
        GROUP BY customer
        HAVING COUNT(*) >= 2
        """,
        {"company": company},
        as_dict=True,
    )

    today = getdate(nowdate())
    result = []

    for row in rows:
        days_ago = date_diff(today, row.last_order_date)
        if days_ago >= inactive_days:
            result.append({
                "customer_id": row.customer_id,
                "customer_name": row.customer_name,
                "last_order_days_ago": days_ago,
            })

    result.sort(key=lambda x: x["last_order_days_ago"], reverse=True)
    return result[:limit] if limit else result


ACTION_PRIORITY = {
    "overdue_invoices": {"label": "Overdue Invoices", "color": "red"},
    "inactive_customers": {"label": "Customers Not Ordered Recently", "color": "orange"},
    "expiring_quotations": {"label": "Quotations Expiring Soon", "color": "yellow"},
    "high_outstanding": {"label": "High Outstanding Customers", "color": "blue"},
    "credit_limit_exceeded": {"label": "Credit Limit Exceeded", "color": "purple"},
}


def _build_action_item(item_type, count, title):
    meta = ACTION_PRIORITY[item_type]
    return {
        "type": item_type,
        "label": meta["label"],
        "color": meta["color"],
        "count": count,
        "title": title,
    }


def get_action_items(company, inactive_days=60, quotation_expiry_days=7, high_outstanding_threshold=100000):
    items = []

    overdue_count = frappe.db.count(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "company": company,
            "outstanding_amount": [">", 0],
            "due_date": ["<", nowdate()],
        },
    )
    if overdue_count:
        items.append(_build_action_item("overdue_invoices", overdue_count, f"{overdue_count} invoice(s) overdue"))

    inactive_customers = get_needs_attention(company, inactive_days=inactive_days, limit=None)
    if inactive_customers:
        items.append(_build_action_item(
            "inactive_customers",
            len(inactive_customers),
            f"{len(inactive_customers)} customer(s) inactive for {inactive_days}+ days",
        ))

    expiring_count = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT q.name)
        FROM `tabQuotation` q
        INNER JOIN `tabCustom Quotation Extended Details` c
            ON c.parent = q.name
        WHERE
            q.docstatus = 1
            AND q.company = %(company)s
            AND c.document_type = 'Quotation'
            AND q.status NOT IN ('Ordered', 'Lost', 'Cancelled', 'Expired')
            AND q.valid_till BETWEEN %(start)s AND %(end)s
        """,
        {
            "company": company,
            "start": nowdate(),
            "end": getdate(nowdate()) + timedelta(days=quotation_expiry_days),
        },
    )[0][0]
    expiring_count = cint(expiring_count)

    if expiring_count:
        items.append(_build_action_item(
            "expiring_quotations",
            expiring_count,
            f"{expiring_count} quotation(s) expiring within {quotation_expiry_days} days",
        ))

    high_outstanding = frappe.db.sql(
        """
        SELECT customer AS customer_id, customer_name, SUM(outstanding_amount) AS total_outstanding
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s AND outstanding_amount > 0
        GROUP BY customer
        HAVING total_outstanding >= %(threshold)s
        ORDER BY total_outstanding DESC
        """,
        {"company": company, "threshold": high_outstanding_threshold},
        as_dict=True,
    )
    if high_outstanding:
        items.append(_build_action_item(
            "high_outstanding",
            len(high_outstanding),
            f"{len(high_outstanding)} customer(s) above outstanding threshold",
        ))

    credit_exceeded = frappe.db.sql(
        """
        SELECT c.name AS customer_id, c.customer_name,
            ccl.credit_limit AS credit_limit,
            COALESCE(SUM(si.outstanding_amount), 0) AS total_outstanding
        FROM `tabCustomer` c
        INNER JOIN `tabCustomer Credit Limit` ccl
            ON ccl.parent = c.name AND ccl.company = %(company)s
        LEFT JOIN `tabSales Invoice` si
            ON si.customer = c.name AND si.docstatus = 1 AND si.company = %(company)s
        WHERE ccl.credit_limit > 0
        GROUP BY c.name, ccl.credit_limit
        HAVING total_outstanding > ccl.credit_limit
        """,
        {"company": company},
        as_dict=True,
    )
    if credit_exceeded:
        items.append(_build_action_item(
            "credit_limit_exceeded",
            len(credit_exceeded),
            f"{len(credit_exceeded)} customer(s) exceeded credit limit",
        ))

    return items


TOP_SALES_SORT_FIELDS = {
    "amount": "base_grand_total",
    "base_grand_total": "base_grand_total",
    "posting_date": "posting_date",
    "customer_name": "customer_name",
}


def get_top_recent_sales(company, order_by=None, limit=5):
    field = "base_grand_total"
    direction = "desc"

    if order_by:
        parts = order_by.strip().split()
        if parts and parts[0] in TOP_SALES_SORT_FIELDS:
            field = TOP_SALES_SORT_FIELDS[parts[0]]
        if len(parts) > 1 and parts[1].lower() in ("asc", "desc"):
            direction = parts[1].lower()

    return frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "company": company},
        fields=[
            "name AS invoice_id", "customer AS customer_id", "customer_name",
            "base_grand_total AS amount", "posting_date", "status", "currency",
        ],
        order_by=f"{field} {direction}",
        limit_page_length=limit,
    )


INVOICE_STATUS_COLORS = {
    "Paid": "green",
    "Unpaid": "orange",
    "Partly Paid": "blue",
    "Overdue": "red",
    "Draft": "gray",
    "Cancelled": "dark_gray",
}


def get_invoice_status_breakdown(company, year):
    rows = frappe.db.sql(
        """
        SELECT status, COUNT(*) AS count
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND company = %(company)s
            AND posting_date BETWEEN %(start)s AND %(end)s
        GROUP BY status
        """,
        {"company": company, "start": f"{year}-01-01", "end": f"{year}-12-31"},
        as_dict=True,
    )

    statuses = [
        {"status": row.status, "count": row.count, "color": INVOICE_STATUS_COLORS.get(row.status, "gray")}
        for row in rows
    ]

    return {"total_invoices": sum(r.count for r in rows), "statuses": statuses}


def get_overdue_invoice_aging(company):
    today = getdate(nowdate())

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "company": company,
            "outstanding_amount": [">", 0],
            "due_date": ["<", today],
        },
        fields=[
            "name AS invoice_id", "customer AS customer_id", "customer_name",
            "outstanding_amount AS amount", "conversion_rate", "due_date",
        ],
    )

    buckets = {"0-30 days": 0.0, "31-60 days": 0.0, "61-90 days": 0.0, "90+ days": 0.0}
    detailed = []

    for inv in invoices:
        days_overdue = date_diff(today, inv.due_date)
        conv_rate = flt(inv.conversion_rate) or 1.0
        amount = flt(inv.amount) * conv_rate  

        if days_overdue <= 30:
            buckets["0-30 days"] += amount
        elif days_overdue <= 60:
            buckets["31-60 days"] += amount
        elif days_overdue <= 90:
            buckets["61-90 days"] += amount
        else:
            buckets["90+ days"] += amount

        detailed.append({
            "customer_id": inv.customer_id,
            "customer_name": inv.customer_name,
            "invoice_id": inv.invoice_id,
            "amount": amount,
            "days_overdue": days_overdue,
        })

    detailed.sort(key=lambda x: x["days_overdue"], reverse=True)

    return {
        "total_overdue": sum(buckets.values()),
        "buckets": [{"range": k, "amount": v} for k, v in buckets.items()],
        "invoices": detailed[:20],
    }


def get_recent_sales_activity(company, limit=10):
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "company": company},
        fields=["name AS reference_id", "customer AS customer_id", "customer_name", "base_grand_total AS amount", "modified AS timestamp"],
        order_by="modified desc",
        limit_page_length=limit,
    )

    payments = frappe.get_all(
        "Payment Entry",
        filters={"docstatus": 1, "company": company, "payment_type": "Receive"},
        fields=["party AS customer_id", "party_name AS customer_name", "reference_no AS reference_id", "paid_amount AS amount", "modified AS timestamp"],
        order_by="modified desc",
        limit_page_length=limit,
    )

    activity = []

    for inv in invoices:
        activity.append({
            "type": "invoice_submitted",
            "title": "Invoice submitted",
            "customer_id": inv.customer_id,
            "customer_name": inv.customer_name,
            "reference_id": inv.reference_id,
            "amount": flt(inv.amount),
            "timestamp": get_datetime(inv.timestamp).isoformat(),
        })

    for pay in payments:
        activity.append({
            "type": "payment_received",
            "title": "Payment received",
            "customer_id": pay.customer_id,
            "customer_name": pay.customer_name,
            "reference_id": pay.reference_id or "",
            "amount": flt(pay.amount),
            "timestamp": get_datetime(pay.timestamp).isoformat(),
        })

    activity.sort(key=lambda x: x["timestamp"], reverse=True)
    return activity[:limit]