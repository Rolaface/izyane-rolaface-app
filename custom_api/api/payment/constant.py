LEDGER_ACCOUNT_TYPE_MAP = {
    "Customer": {"from": ["Bank", "Cash"], "to": ["Receivable"]},
    "Supplier": {"from": ["Bank", "Cash"], "to": ["Payable"]},
    "Employee": {"from": ["Bank", "Cash"], "to": ["Payable"]},
    "Shareholder": {"from": ["Bank", "Cash", "Equity"], "to": ["Payable", "Equity"]},
    "Internal Transfer": {"from": ["Bank", "Cash"], "to": ["Bank", "Cash"]},
}