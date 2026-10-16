import frappe
from frappe.desk.doctype.tag.tag import DocTags, update_tags
from frappe.utils import unique


class PdcDocTags(DocTags):
    """
    DocTags with an ignore_permissions flag. When False, Frappe's original
    update() runs (write permission required on the tagged document); when
    True, the write check on the tagged document is skipped.
    """

    def __init__(self, dt, ignore_permissions=False):
        super().__init__(dt)
        self.ignore_permissions = ignore_permissions

    def update(self, dn, tl):
        if not self.ignore_permissions:
            return super().update(dn, tl)

        tags = ",".join(unique(t for t in tl if t))
        frappe.db.set_value(self.dt, dn, "_user_tags", tags, update_modified=False)
        doc = frappe.get_doc(self.dt, dn)
        doc.flags.ignore_permissions = True
        update_tags(doc, tags)
