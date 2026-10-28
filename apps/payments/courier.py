"""Razorpay adapter for separately payable post-dispatch courier charges.

Dormant without an enabled connection. Captures must match the provider order,
amount, currency and mode; a test capture never clears the real receivable.
"""
import hashlib,hmac,re
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from apps.orders.models import CourierCharge
from apps.orders.courier import confirm_courier_payment
from .models import CourierPayment
from .provider import Razorpay,PaymentError
from .services import active_connection,_paise,_order_evidence


def client(intent):
    if intent.connection.key_id!=intent.key_id:
        raise PaymentError('The courier payment credentials changed. Ask the kitchen to reconcile this payment.')
    return Razorpay(intent.connection)


def start(charge):
    with transaction.atomic():
        charge=CourierCharge.objects.select_for_update().select_related('order').get(pk=charge.pk)
        if not charge.dispatched_at or charge.amount is None or charge.amount<=0 or charge.paid_at or charge.order.status=='cancelled':
            raise PaymentError('This courier charge is not awaiting payment.')
        if charge.order.payment_status!='paid':
            raise PaymentError('Complete the food order payment before paying the separate courier charge.')
        if not (charge.order.tenant.config.checkout_settings or {}).get('courier_online_enabled',False):
            raise PaymentError('Courier online payments are offline. Arrange payment with the kitchen.')
        connection=active_connection()
        if not connection:raise PaymentError('Online payment is offline. Arrange courier payment with the kitchen.')
        intent,_=CourierPayment.objects.get_or_create(charge=charge,mode=connection.mode,
            defaults={'connection':connection,'key_id':connection.key_id,'amount':_paise(charge.amount)})
        if intent.amount!=_paise(charge.amount):raise PaymentError('Courier amount changed. Contact the kitchen.')
        if intent.state in ('ready','captured'):return intent
        if intent.state=='creating' and intent.updated_at>timezone.now()-timedelta(seconds=30):
            raise PaymentError('Courier payment setup is in progress. Check again shortly.')
        recovery=intent.state in ('creating','uncertain')
        intent.state='creating';intent.save(update_fields=['state','updated_at'])
    try:
        api=client(intent)
        evidence=api.find_order(intent) if recovery else api.create_order(intent)
        if not evidence:raise PaymentError('Courier payment setup is awaiting provider reconciliation. Do not create another payment.',uncertain=True)
        provider_id=_order_evidence(intent,evidence)
    except (PaymentError,RuntimeError):
        CourierPayment.objects.filter(pk=intent.pk,state='creating').update(state='uncertain')
        raise
    with transaction.atomic():
        intent=CourierPayment.objects.select_for_update().get(pk=intent.pk)
        intent.provider_order_id=provider_id;intent.state='ready';intent.save()
    return intent


@transaction.atomic
def apply_capture(intent,entity):
    intent=CourierPayment.objects.select_for_update().select_related('charge__order','connection').get(pk=intent.pk)
    if (entity.get('order_id')!=intent.provider_order_id or type(entity.get('amount')) is not int or entity['amount']!=intent.amount or entity.get('currency')!=intent.currency):
        raise PaymentError('Courier payment amount or order did not match.')
    payment_id=Razorpay.identifier(entity.get('id'),'pay')
    if intent.payment_id and intent.payment_id!=payment_id:raise PaymentError('Courier payment reference did not match.')
    if entity.get('status')=='failed':return intent
    if entity.get('status')!='captured' or entity.get('captured') is not True:return intent
    if intent.state=='captured':return intent
    intent.payment_id=payment_id;intent.state='captured';intent.captured_at=timezone.now();intent.save()
    if intent.mode=='live':
        confirm_courier_payment(intent.charge.order,reference=payment_id,actor='razorpay')
    return intent


def verify(intent,provider_order,payment_id,signature):
    if provider_order!=intent.provider_order_id:raise PaymentError('Courier payment order did not match.')
    api=client(intent)
    expected=hmac.new(api.secret.encode(),f'{provider_order}|{payment_id}'.encode(),hashlib.sha256).hexdigest()
    if not isinstance(signature,str) or not re.fullmatch('[0-9a-f]{64}',signature) or not hmac.compare_digest(expected,signature):
        raise PaymentError('Invalid courier payment signature.')
    return apply_capture(intent,api.payment(Razorpay.identifier(payment_id,'pay')))


def reconcile(intent):
    if not intent.provider_order_id:return intent
    for payment in client(intent).order_payments(intent):
        if payment.get('status')=='captured':return apply_capture(intent,payment)
    return intent
