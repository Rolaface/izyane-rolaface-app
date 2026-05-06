import frappe
from custom_api.utils.response import send_old_response, send_response, send_response_list
from erpnext.accounts.doctype.account.account import get_account_currency
from erpnext.accounts.doctype.bank_account.bank_account import (
    get_default_company_bank_account,
    get_party_bank_account,
)
from erpnext.accounts.party import get_party_account
from frappe.desk.search import build_for_autosuggest, search_widget
# from erpnext.zra_client.generic_api import send_response as old_response
def _get_pagination_args():
    try:
        page = int(frappe.request.args.get("page", 1))
        page_size = int(frappe.request.args.get("page_size", 10))
    except ValueError:
        page, page_size = 1, 10
    return page, page_size

def _fetch_paginated_autosuggest(
    doctype,
    filters=None,
    search_fields=None,
    field_map=None,
):
    txt = frappe.request.args.get("search", "").strip()
    page, page_size = _get_pagination_args()
    start = (page - 1) * page_size

    filters = filters or {}
    search_fields = search_fields or ["name"]

    or_filters = []
    if txt:
        for field in search_fields:
            or_filters.append([doctype, field, "like", f"%{txt}%"])

    required_fields = {"name"}
    if field_map:
        for value in field_map.values():
            if isinstance(value, str):
                required_fields.add(value)
            elif isinstance(value, (list, tuple)):
                required_fields.update(value)

    rows = frappe.get_all(
        doctype,
        filters=filters,
        or_filters=or_filters if txt else None,
        fields=list(required_fields),
        limit_start=start,
        limit_page_length=page_size,
        order_by="modified desc",
    )

    def resolve(row, mapper):
        if callable(mapper):
            return mapper(row)
        if isinstance(mapper, str):
            return row.get(mapper)
        if isinstance(mapper, (list, tuple)):
            return " ".join(str(row.get(f) or "") for f in mapper).strip()
        return None

    response_data = []
    for row in rows:
        if field_map:
            item = {key: resolve(row, mapper) for key, mapper in field_map.items()}
        else:
            item = {
                "value": row.get("name"),
                "label": row.get("name"),
                "description": row.get("name"),
            }
        response_data.append(item)

    if txt and search_fields:
        count_result = frappe.get_all(
            doctype,
            filters=filters,
            or_filters=or_filters,
            fields=[{"COUNT": "name"}],
            as_list=True,
        )
        total_items = count_result[0][0] if count_result and count_result[0] else 0
    else:
        total_items = frappe.db.count(doctype, filters=filters)

    total_pages = ((total_items + page_size - 1) // page_size if page_size else 1)

    return {
        "data": response_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "items_in_page": len(response_data),
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_payable_accounts():
    try:
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict(
            {"company": company, "account_type": "Payable", "is_group": 0}
        )
        data = _fetch_paginated_autosuggest(
            "Account", filters, ["name", "account_name"]
        )
        return send_response_list(
            "success", "Payable Accounts fetched successfully.", data
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Payable Accounts API Error")
        return send_response("fail", str(e), None, 500, 500)


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_receivable_accounts():
    try:
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict(
            {"company": company, "account_type": "Receivable", "is_group": 0}
        )
        data = _fetch_paginated_autosuggest(
            "Account", filters, ["name", "account_name"]
        )
        return send_response_list(
            "success", "Receivable Accounts fetched successfully.", data
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Receivable Accounts API Error")
        return send_response("fail", str(e), None, 500, 500)


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_cost_centers():
    try:
        company = frappe.defaults.get_user_default("Company")
        filters = frappe._dict({"company": company})
        data = _fetch_paginated_autosuggest(
            "Cost Center", filters, ["name", "cost_center_name"]
        )
        return send_response_list("success", "Cost Centers fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Cost Centers API Error")
        return send_response("fail", str(e), None, 500, 500)


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customers():
    try:
        data = _fetch_paginated_autosuggest(
            doctype="Customer",
            filters=frappe._dict({}),
            search_fields=["name", "customer_name"],
            field_map={
                "value": "name",
                "label": "customer_name",
                "description": "name",
            },
        )
        return send_response_list("success", "Customers fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Customers API Error")
        return send_response("fail", str(e), None, 500, 500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_customers_group():
    try:
        data = _fetch_paginated_autosuggest(
            "Customer Group", frappe._dict({}), ["name", "customer_group_name"]
        )
        return send_response_list("success", "Customers Group fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Customers Group API Error")
        return send_response("fail", str(e), None, 500, 500)


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_suppliers():
    try:
        data = _fetch_paginated_autosuggest(
            doctype="Supplier",
            filters=frappe._dict({}),
            search_fields=["name", "supplier_name"],
            field_map={
                "value": "name",
                "label": "supplier_name",
                "description": "name",
            },
        )

        return send_response_list("success","Suppliers fetched successfully.",data,)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Get Suppliers API Error")
        return send_response("fail",str(e),None,500,500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_locations():
    try:
        data = _fetch_paginated_autosuggest(
            doctype="Location",
            filters=frappe._dict({}),
            search_fields=["name", "location_name"],
            field_map={
                "value": "name",
                "label": "location_name",
                "description": "name",
            },
        )

        return send_response_list("success","Locations fetched successfully.",data,)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Get Locations API Error")
        return send_response("fail",str(e),None,500,500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_employees():
    try:
        data = _fetch_paginated_autosuggest(
            doctype="Employee",
            filters=frappe._dict({}),
            search_fields=["name", "employee_name"],
            field_map={
                "value": "name",
                "label": "employee_name",
                "description": "name",
            },
        )

        return send_response_list("success","Employees fetched successfully.",data,)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(),"Get Employees API Error")
        return send_response("fail",str(e),None,500,500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_items():
    try:
        filters = frappe._dict({})

        is_fixed_asset = frappe.request.args.get("is_fixed_asset")
        if is_fixed_asset is not None:
            filters["is_fixed_asset"] = int(is_fixed_asset)

        data = _fetch_paginated_autosuggest(
            doctype="Item",
            filters=filters,
            search_fields=["name", "item_name"],
            field_map={
                "value": "name",
                "label": "item_name",
                "description": "name",
            },
        )

        return send_response_list(
            "success", "Item Codes fetched successfully.", data
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Item Codes API Error")
        return send_response("fail", str(e), None, 500, 500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_suppliers_group():
    try:
        data = _fetch_paginated_autosuggest(
            "Supplier Group", frappe._dict({}), ["name", "supplier_group_name"]
        )
        return send_response_list("success", "Supplier Group fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Supplier Group API Error")
        return send_response("fail", str(e), None, 500, 500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_item_groups():
    try:
        data = _fetch_paginated_autosuggest(
            "Item Group", frappe._dict({}), ["name", "item_group_name"]
        )
        return send_response_list("success", "Item Groups fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Item Groups API Error")
        return send_response("fail", str(e), None, 500, 500)
    
@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_incoterms():
    try:
        data = _fetch_paginated_autosuggest(
            "Incoterm", frappe._dict({}), ["name", "title"]
        )
        data = _fetch_paginated_autosuggest(
            doctype="Incoterm",
            filters=frappe._dict({}),
            search_fields=["name", "code", "title"],
            field_map={
                "value": "code",
                "label": "title",
                "description": "description",
            },
        )
        return send_response_list("success", "Incoterms fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Incoterms API Error")
        return send_response("fail", str(e), None, 500, 500)

@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_shipping_rules():
    try:
        data = _fetch_paginated_autosuggest(
            "Shipping Rule", frappe._dict({}), ["name", "shipping_rule_type"]
        )
        return send_response_list("success", "Shipping Rule fetched successfully.", data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Shipping Rule API Error")
        return send_response("fail", str(e), None, 500, 500)



@frappe.whitelist(allow_guest=False, methods=["GET"])
def parties_and_accounts():
    try:
        txt = frappe.request.args.get("search", "")
        doc_filter = frappe.request.args.get("filter", "")
        reference_doctype = frappe.request.args.get(
            "reference_doctype", "Bank Account"
        )  # We have made Bank Account as default because API was initially develop for referebce doctye = Bank Account and because of so much update in the front-end we have make it default
        company = frappe.defaults.get_user_default("Company")
        filters = None

        if reference_doctype not in ["Bank Account", "Payment Entry"]:
            return send_response(
                status="fail",
                message="Invalid Reference Doctype.",
                status_code=400,
                http_status=400,
            )
        if doc_filter not in [
            "Company",
            "Supplier",
            "Bank",
            "Customer",
            "Currency",
            "Account",
            "Shareholder",
            "Employee",
        ]:
            return send_response(
                status="fail",
                message="Invalid Filter.",
                status_code=400,
                http_status=400,
            )

        if doc_filter == "Company":
            currency = frappe.db.get_value("Company", company, "default_currency")
            response = {"company": company, "currency": currency}
        else:
            filter_fields = None
            if doc_filter in ["Supplier", "Customer"]:
                filter_fields = '["default_currency"]'
            if doc_filter in ["Currency"]:
                filter_fields = '["default_currency", "symbol", "number_format"]'
            if doc_filter == "Bank":
                filter_fields = '["swift_number"]'

            if doc_filter == "Account":
                filters = frappe._dict(
                    {"account_type": "Bank", "company": company, "is_group": 0}
                )

            response = search_widget(
                doc_filter,
                txt.strip(),
                None,
                searchfield=None,
                page_length=10,
                filters=filters,
                filter_fields=filter_fields,
                reference_doctype=reference_doctype,
                ignore_user_permissions=0,
                as_dict=True,
            )

        return send_response(
            status="success",
            message="Suppliers fetched successfully.",
            data={"data": response},
            status_code=200,
            http_status=200,
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Suppliers API Error")
        return send_old_response(
            status="fail", message=str(e), data=None, status_code=500, http_status=500
        )


# Below is the custome API of "payment_entry.payment_entry.get_party_details"
@frappe.whitelist(allow_guest=False, methods=["POST"])
def get_party_details(party_type, party, cost_center=None):
    company_default_bank_account = ""
    party_bank_account = ""
    company_account_ledger = company_account_ledger_currency = party_bank_account_details = ""

    company = frappe.defaults.get_user_default("Company")
    company_currency = frappe.defaults.get_user_default("Currency")
    if not frappe.db.exists(party_type, party):
        return send_response(
            status="fail",
            message=f"Party {party} does not exist",
            data=None,
            status_code=400,
            http_status=400,
        )

    party_account = get_party_account(party_type, party, company)
    account_currency = get_account_currency(party_account)
    _party_name = (
        "title" if party_type == "Shareholder" else party_type.lower() + "_name"
    )
    party_name = frappe.db.get_value(party_type, party, _party_name)
    if party_type in ["Customer", "Supplier"]:
        party_bank_account = get_party_bank_account(party_type, party)
        company_default_bank_account = get_default_company_bank_account(
            company, party_type, party
        )
        if company_default_bank_account:
            company_account_ledger = frappe.get_cached_value(
                "Bank Account",
                company_default_bank_account,
                ["account", "bank", "bank_account_no", "account_name"],
                as_dict=1,
            )
            company_account_ledger_currency = (
                frappe.db.get_value(
                    "Account", company_account_ledger["account"], "account_currency"
                )
                if company_account_ledger["account"]
                else None
            )
        if party_bank_account:
            party_bank_account_details = frappe.get_cached_value(
                                            "Bank Account",
                                            company_default_bank_account,
                                            ["bank", "account_name"],
                                            as_dict=1,
                                        )
    total_outstanding = 0

    if party_type == "Customer":
        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"customer": party, "docstatus": 1},
            fields=["outstanding_amount"]
        )
        total_outstanding = sum(inv.get("outstanding_amount", 0) or 0 for inv in invoices)

    elif party_type == "Supplier":
        invoices = frappe.get_all(
            "Purchase Invoice",
            filters={"supplier": party, "docstatus": 1},
            fields=["outstanding_amount"]
        )
        total_outstanding = sum(inv.get("outstanding_amount", 0) or 0 for inv in invoices)


    return send_response(
        status="success",
        message="Bank Account created successfully.",
        data={
            "party_ledger_account": party_account,
            "party_name": party_name,
            "party": {
                        "id": party_bank_account,
                        "name": f"{party_bank_account_details["account_name"]} - {party_bank_account_details["bank"]}" if party_bank_account_details else None
                    },
            "party_account_currency": account_currency,
            # "party_bank_account": party_bank_account,
            "company":{
                        "id": company_default_bank_account,
                        "name": f"{company_account_ledger["account_name"]} - {company_account_ledger["bank"]}" if company_account_ledger else None,
                      },
            # "company_bank_account_id": company_default_bank_account,
            # "company_bank_account_display_name": f"{company_account_ledger["account_name"]} {company_account_ledger["bank"]}-{company_account_ledger_currency}",
            "company_account_ledger": company_account_ledger["account"] if company_account_ledger else None,
            "company_account_ledger_currency": company_account_ledger_currency,
            "company_default_currency": company_currency,
            "total_outstanding_amount": total_outstanding
        },
        status_code=201,
        http_status=201,
    )


@frappe.whitelist(allow_guest=False, methods=["GET"])
def get_currencies():
    try:
        txt = frappe.request.args.get("search", "").strip()
        
        try:
            page = int(frappe.request.args.get("page", 1))
            page_size = int(frappe.request.args.get("page_size", 10))
        except ValueError:
            page, page_size = 1, 10

        start = (page - 1) * page_size

        filters = {}
        if txt:
            filters = [
                ["Currency", "name", "like", f"%{txt}%"],
                ["Currency", "currency_name", "like", f"%{txt}%"]
            ]

        total_items = frappe.db.count("Currency", filters=filters)
        
        rows = frappe.get_all(
            "Currency",
            filters=filters,
            or_filters=filters if txt else None,
            fields=["name", "currency_name", "number_format", "symbol"],
            order_by="name asc",
            limit_start=start,
            limit_page_length=page_size
        )

        data = [
            {
                "name": row.name,
                "currency_name": row.currency_name,
                "symbol": row.symbol,
                "number_format": row.number_format,
            }
            for row in rows
        ]

        total_pages = (total_items + page_size - 1) // page_size if page_size else 1

        return send_response_list(
            status="success",
            message="Currencies fetched successfully.",
            data={
                "data": data,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "items_in_page": len(data),
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_previous": page > 1,
                },
            },
            status_code=200,
            http_status=200,
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Currencies API Error")
        return send_response_list(
            status="fail",
            message=str(e),
            data=None,
            status_code=500,
            http_status=500,
        )
