# custom_api/api/item_classification_import.py
#
# Bulk import for "Custom Item Classification" (ZRA UNSPSC classification codes).
# One-time import, but written to be fast + error-tolerant + progress-tracked
# since the file can have thousands of rows.
#
# Flow:
#   1. import_item_classification() - whitelisted endpoint, accepts the uploaded
#      file, kicks off a background job, returns immediately with a job_id.
#   2. run_import() - does the actual work in batches, publishes progress via
#      frappe.publish_realtime so the frontend can drive a progress bar.

import csv
import frappe
from frappe.utils import cint, now


@frappe.whitelist()
def import_item_classification():
    """
    POST endpoint. Send the CSV as multipart/form-data under key 'file'.
    Returns a job_id immediately; actual import happens in background.
    """
    uploaded_file = frappe.request.files.get("file")
    if not uploaded_file:
        frappe.throw("No file provided. Send it under form-data key 'file'.")

    content = uploaded_file.stream.read()
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": uploaded_file.filename,
        "content": content,
        "is_private": 1,
    })
    file_doc.save(ignore_permissions=True)

    job_id = frappe.generate_hash(length=10)

    frappe.enqueue(
        method="custom_api.api.item_classification_import.run_import",
        queue="long",
        timeout=3600,
        job_id=job_id,
        file_url=file_doc.file_url,
        user=frappe.session.user,
    )

    return {"job_id": job_id, "message": "Import started"}


def run_import(file_url, user):
    file_doc = frappe.get_doc("File", {"file_url": file_url})
    file_path = file_doc.get_full_path()

    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    if total == 0:
        _notify(user, 100, 0, 0, ["File is empty"], done=True)
        return

    # fresh import every run: wipe existing data first
    frappe.db.truncate("Custom Item Classification")
    frappe.db.commit()

    # still guard against duplicate codes appearing twice WITHIN the same
    # CSV (table itself is empty right after truncate)
    existing_codes = set()

    BATCH_SIZE = 500
    inserted = 0
    skipped = 0
    errors = []
    batch = []

    for i, row in enumerate(rows, start=1):
        code = (row.get("itemClsCd") or "").strip()
        name = (row.get("itemClsNm") or "").strip()
        level = cint(row.get("itemClsLvl") or 0)
        is_active = 1 if (row.get("useYn") or "True").strip().lower() in ("true", "1", "yes") else 0

        if not code:
            skipped += 1
            errors.append(f"Row {i}: missing itemClsCd")
            continue

        if code in existing_codes:
            skipped += 1
            continue

        ts = now()
        batch.append({
            "name": code,              # class_code is unique anyway, use it as docname
            "class_code": code,
            "class_name": name,
            "class_level": level,
            "is_active": is_active,
            "docstatus": 0,
            "idx": 0,
            "owner": user,
            "modified_by": user,
            "creation": ts,
            "modified": ts,
        })
        existing_codes.add(code)

        if len(batch) >= BATCH_SIZE or i == total:
            try:
                frappe.db.bulk_insert(
                    "Custom Item Classification",
                    fields=list(batch[0].keys()),
                    values=[list(v.values()) for v in batch],
                    ignore_duplicates=True,
                )
                inserted += len(batch)
                frappe.db.commit()
            except Exception:
                # fall back to row-by-row for this batch so one bad row
                # doesn't kill the whole batch
                for v in batch:
                    try:
                        frappe.db.sql(
                            """INSERT IGNORE INTO `tabCustom Item Classification`
                               (name, class_code, class_name, class_level, is_active,
                                docstatus, idx, owner, modified_by, creation, modified)
                               VALUES (%(name)s, %(class_code)s, %(class_name)s, %(class_level)s,
                                       %(is_active)s, %(docstatus)s, %(idx)s, %(owner)s,
                                       %(modified_by)s, %(creation)s, %(modified)s)""",
                            v,
                        )
                        inserted += 1
                    except Exception as e:
                        skipped += 1
                        errors.append(f"{v['class_code']}: {e}")
                frappe.db.commit()

            batch = []
            pct = int((i / total) * 100)
            _notify(user, pct, inserted, skipped, errors[-5:])

    _notify(user, 100, inserted, skipped, errors, done=True)


def _notify(user, pct, inserted, skipped, errors, done=False):
    frappe.publish_realtime(
        event="item_classification_import_progress",
        message={
            "progress": pct,
            "inserted": inserted,
            "skipped": skipped,
            "recent_errors": errors,
            "done": done,
        },
        user=user,
    )
