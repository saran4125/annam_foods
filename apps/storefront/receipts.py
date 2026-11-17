"""Browser receipt state: reads scoped records, never trusts customer payment flags."""
from django.urls import reverse
from apps.billing.models import Invoice, InvoiceKind
from apps.payments.models import PaymentIntent


def receipt_state(order, reference):
    intent = PaymentIntent.objects.filter(order=order).first()
    test = bool(intent and intent.mode == 'test')
    invoice = Invoice.objects.filter(order=order).exclude(kind=InvoiceKind.CREDIT_NOTE).first()
    downloadable = (test and intent.state == 'captured' and order.payment_status == 'paid') or (
        not test and invoice and order.payment_status in ('paid', 'refunded'))
    return {'paid': order.payment_status == 'paid', 'status': order.payment_status,
            'order_status': order.status, 'payment_label': order.get_payment_status_display(),
            'order_label': order.get_status_display(), 'test': test,
            'invoice_url': reverse('storefront:customer_bill', args=[reference]) if invoice and not test else '',
            'download_url': reverse('storefront:customer_pdf', args=[reference]) if downloadable else ''}
