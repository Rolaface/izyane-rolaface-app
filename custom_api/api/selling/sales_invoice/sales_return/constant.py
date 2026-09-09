ALLOWED_FIELDS = frozenset({
    "posting_date", "due_date", "po_no", "cost_center", "tax_category",
    "currency", "conversion_rate", "shipping_address_name", "customer_address",
    "set_warehouse",
})

SORT_FIELDS = frozenset({
    "name", "creation", "modified", "posting_date", "grand_total",
    "outstanding_amount", "customer_name",
})

LIST_FIELDS = [
    "name", "customer", "customer_name", "posting_date", "due_date",
    "return_against", "grand_total", "outstanding_amount", "status",
    "docstatus", "is_return", "is_debit_note", "currency", "tax_category",
    "creation", "modified",
]

DOC_TYPES = {"Credit Note", "Debit Note"}
ACTIONS = {"approved", "cancelled", "amend"}
