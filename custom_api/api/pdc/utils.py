def build_pi_filters(args):

    frappe_filters = {}

    if not args:
        return frappe_filters

    if args.get("status"):
        mapped_statuses = []
        status = args.get("status")
        status_filters = status.split(",") if isinstance(status, str) else status
        for status_filter in status_filters:
            mapped_statuses.append(status_filter)
        frappe_filters["status"] = ["in", mapped_statuses]

    if args.get("from_date") and args.get("to_date"):
        frappe_filters["cheque_date"] = ["between", [args["from_date"], args["to_date"]]]

    if args.get("company"):
        frappe_filters["company"] = args["company"]

    return frappe_filters