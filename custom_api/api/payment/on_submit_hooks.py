from custom_api.api.payment.utils import mark_reference_pdc_used

def on_submit(doc, method=None):
    mark_reference_pdc_used(doc.reference_no)
