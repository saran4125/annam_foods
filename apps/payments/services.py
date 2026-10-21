"""Razorpay state changes: fetched evidence, row locks and retry-safe financial records."""
import hashlib
import hmac
import re
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceKind
from apps.billing.services import issue_bill, issue_credit_note
from apps.orders.models import Order, OrderEvent, PaymentMode, PaymentStatus
from apps.tenancy.models import TenantUser
from .models import RazorpayConnection, PaymentIntent, Refund, PaymentEvent
from .provider import Razorpay, PaymentError


def require_finance_owner(user, tenant):
    if not user.is_authenticated or not user.is_active or not (user.is_superuser or
            TenantUser.objects.filter(user=user, tenant=tenant, role='owner').exists()):
        raise PermissionDenied('Only the kitchen owner may change payment credentials or request refunds.')


def active_connection():
    return RazorpayConnection.objects.filter(enabled=True).first()


def payment_choices(tenant):
    choices = []
    if active_connection():
        choices.append(('online', 'Pay online with Razorpay'))
    if tenant.feature('manual_payments'):
        choices.append(('manual', 'Arrange payment with the kitchen'))
    return choices


def _client(intent):
    connection = RazorpayConnection.objects.get(pk=intent.connection_id)
    if connection.key_id != intent.key_id and intent.state not in ('captured', 'part_refunded', 'refund_pending', 'refunded'):
        raise PaymentError('The keys for this payment changed. Contact the kitchen to reconcile it with Razorpay.')
    try:
        return Razorpay(connection)
    except RuntimeError:
        raise PaymentError('Payment credentials could not be read. Please contact the kitchen.') from None


def _paise(total):
    value = Decimal(total) * 100
    if not value.is_finite() or value != value.to_integral_value() or not 100 <= value <= 100000000:
        raise PaymentError('This amount cannot be paid through online checkout. Contact the kitchen.')
    return int(value)


def _order_evidence(intent, entity):
    if (entity.get('receipt') != intent.receipt or type(entity.get('amount')) is not int or entity['amount'] != intent.amount
            or entity.get('currency') != intent.currency):
        raise PaymentError('Razorpay order details did not match this order.')
    return Razorpay.identifier(entity.get('id'), 'order')


def start_payment(order):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.payment_mode != PaymentMode.ONLINE or order.status == 'cancelled' or order.payment_status in ('paid', 'refunded'):
            raise PaymentError('This order is not awaiting an online payment.')
        intent = PaymentIntent.objects.filter(order=order).first()
        if intent is None:
            connection = active_connection()
            if not connection:
                raise PaymentError('Online payment is currently unavailable. Contact the kitchen.')
            intent = PaymentIntent.objects.create(order=order, connection=connection, key_id=connection.key_id,
                mode=connection.mode, amount=_paise(order.total))
        if intent.state in ('new', 'error') and intent.key_id != intent.connection.key_id:
            intent.key_id = intent.connection.key_id
            intent.save(update_fields=['key_id', 'updated_at'])
        if intent.state in ('ready', 'captured', 'part_refunded', 'refunded'):
            return intent
        if intent.state == 'creating':
            # A crashed worker is reconciled by receipt, never by blindly creating another order.
            if (timezone.now() - intent.updated_at).total_seconds() < 30:
                raise PaymentError('Payment setup is in progress. Check its status in a moment.')
            intent.state = 'uncertain'
        reconcile = intent.state == 'uncertain'
        intent.state = 'creating'
        intent.save(update_fields=['state', 'updated_at'])
    try:
        client = _client(intent)
        entity = client.find_order(intent) if reconcile else client.create_order(intent)
        if entity is None:
            raise PaymentError('Payment setup is still being checked. Contact the kitchen before starting another payment.', uncertain=True)
        try:
            provider_id = _order_evidence(intent, entity)
        except PaymentError as exc:
            exc.uncertain = True
            raise
    except PaymentError as exc:
        PaymentIntent.objects.filter(pk=intent.pk, state='creating').update(state='uncertain' if exc.uncertain or reconcile else 'error', updated_at=timezone.now())
        raise
    with transaction.atomic():
        Order.objects.select_for_update().get(pk=order.pk)
        intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
        if intent.state not in ('captured', 'refunded', 'part_refunded'):
            intent.provider_order_id, intent.state = provider_id, 'ready'
            intent.save(update_fields=['provider_order_id', 'state', 'updated_at'])
    return intent


def _try_bill(intent, order):
    if intent.mode != 'live' or order.payment_status != 'paid':
        return
    try:
        with transaction.atomic():
            issue_bill(order)
    except (ValueError, ValidationError):
        intent.bill_error = 'Payment received. Complete billing settings, then generate the bill from the order.'
    else:
        intent.bill_error = ''


def _full_refund(intent, order):
    if order.payment_status != PaymentStatus.REFUNDED:
        order.payment_status = PaymentStatus.REFUNDED
        order.save(update_fields=['payment_status'])
        OrderEvent.objects.create(order=order, from_status=order.status, to_status=order.status,
            actor='razorpay', note='Full Razorpay refund confirmed.')
    intent.state, intent.refunded_amount = 'refunded', intent.amount
    invoice = Invoice.objects.filter(order=order).exclude(kind=InvoiceKind.CREDIT_NOTE).first()
    if invoice and not intent.credit_note_id:
        credits = list(Invoice.objects.filter(original=invoice, kind=InvoiceKind.CREDIT_NOTE))
        remaining = invoice.total - sum((credit.total for credit in credits), Decimal('0'))
        if remaining > 0:
            intent.credit_note = issue_credit_note(invoice, amount=remaining, reason='Razorpay full refund')
        elif credits:
            intent.credit_note = credits[-1]


def _payment_evidence(intent, entity):
    Razorpay.identifier(entity.get('id'), 'pay')
    if (entity.get('order_id') != intent.provider_order_id or type(entity.get('amount')) is not int
            or entity['amount'] != intent.amount or entity.get('currency') != intent.currency):
        raise PaymentError('Razorpay payment details did not match this order.')


@transaction.atomic
def apply_payment(intent, entity):
    order = Order.objects.select_for_update().get(pk=intent.order_id)
    intent = PaymentIntent.objects.select_for_update().get(pk=intent.pk)
    _payment_evidence(intent, entity)
    status = entity.get('status')
    if status not in ('captured', 'refunded'):
        if status in ('failed', 'authorized') and order.payment_status not in ('paid', 'refunded'):
            next_status = PaymentStatus.FAILED if status == 'failed' else PaymentStatus.PENDING
            if order.payment_status != next_status:
                order.payment_status = next_status
                order.save(update_fields=['payment_status'])
                if status == 'failed':
                    OrderEvent.objects.create(order=order, from_status=order.status, to_status=order.status, actor='razorpay', note='Payment attempt failed; the same order can be retried.')
        return intent
    if entity.get('captured') is not True:
        raise PaymentError('Razorpay has not confirmed capture yet.')
    if intent.payment_id and intent.payment_id != entity['id']:
        raise PaymentError('This order already has a different captured payment. Contact the kitchen.')
    refunded = entity.get('amount_refunded', 0)
    if type(refunded) is not int or not 0 <= refunded <= intent.amount:
        raise PaymentError('Invalid refund amount reported by Razorpay.')
    intent.payment_id = entity['id']
    intent.refunded_amount = max(intent.refunded_amount, refunded)
    processed_refunds = 0
    if refunded and intent.state != 'refunded':
        for item in _client(intent).refunds(intent):
            if (item.get('payment_id') == intent.payment_id and item.get('status') == 'processed'
                    and type(item.get('amount')) is int and 0 < item['amount'] <= intent.amount):
                processed_refunds += item['amount']
    if order.payment_status != 'refunded' and processed_refunds < intent.amount:
        if order.payment_status != 'paid':
            order.payment_status, order.payment_reference = PaymentStatus.PAID, entity['id']
            order.save(update_fields=['payment_status', 'payment_reference'])
            note = ('TEST payment captured; no real money collected.' if intent.mode == 'test' else 'Razorpay captured payment verified.')
            if order.status == 'cancelled':
                note += ' Order cancelled: review refund.'
            OrderEvent.objects.create(order=order, from_status=order.status, to_status=order.status, actor='razorpay', note=note)
        intent.state = ('part_refunded' if processed_refunds else 'refund_pending') if intent.refunded_amount else 'captured'
        _try_bill(intent, order)
    else:
        _full_refund(intent, order)
    intent.save()
    return intent


def verify_checkout(intent, provider_order, payment_id, signature):
    if provider_order != intent.provider_order_id:
        raise PaymentError('Payment order reference did not match.')
    client = _client(intent)
    expected = hmac.new(client.secret.encode(), f'{intent.provider_order_id}|{payment_id}'.encode(), hashlib.sha256).hexdigest()
    if not isinstance(signature, str) or not re.fullmatch(r'[0-9a-f]{64}', signature) or not hmac.compare_digest(expected, signature):
        raise PaymentError('Payment signature verification failed.')
    entity = client.payment(payment_id)
    return apply_payment(intent, entity)


def reconcile_payment(intent):
    if not intent.provider_order_id:
        return start_payment(intent.order)
    entities = _client(intent).order_payments(intent)
    for entity in sorted(entities, key=lambda e: e.get('status') not in ('captured', 'refunded')):
        result = apply_payment(intent, entity)
        if result.state in ('captured', 'refunded', 'part_refunded'):
            return result
    return PaymentIntent.objects.get(pk=intent.pk)


def request_refund(order, *, actor, reason):
    require_finance_owner(actor, order.tenant)
    if not reason.strip():
        raise PaymentError('Enter a reason for this full refund.')
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        intent = PaymentIntent.objects.select_for_update().get(order=order)
        if order.payment_status != 'paid' or not intent.payment_id or intent.refunded_amount:
            raise PaymentError('Only a fully paid, unrefunded Razorpay payment can receive a full refund here.')
        refund = Refund.objects.exclude(state='failed').filter(intent=intent).first()
        if refund:
            return refresh_refund(refund)
        refund = Refund.objects.create(intent=intent, amount=intent.amount, reason=reason.strip()[:200], actor=str(actor.pk))
    # Recheck provider-side refunds before requesting money back.
    try:
        entity = _client(intent).payment(intent.payment_id)
        _payment_evidence(intent, entity)
        if entity.get('status') != 'captured' or entity.get('captured') is not True:
            raise PaymentError('Razorpay has not confirmed a refundable captured payment.')
        if entity.get('amount_refunded', 0):
            Refund.objects.filter(pk=refund.pk).update(state='failed')
            raise PaymentError('Razorpay already reports a refund. Refresh payment status before proceeding.')
        with transaction.atomic():
            locked = Refund.objects.select_for_update().get(pk=refund.pk)
            if locked.state != 'requested':
                return locked
            locked.state = 'submitting'
            locked.save(update_fields=['state', 'updated_at'])
        result = _client(intent).refund(intent, refund)
    except PaymentError as exc:
        Refund.objects.filter(pk=refund.pk, state='requested').update(state='failed', updated_at=timezone.now())
        Refund.objects.filter(pk=refund.pk, state='submitting').update(state='uncertain' if exc.uncertain else 'failed', updated_at=timezone.now())
        raise
    return apply_refund(refund, result)


@transaction.atomic
def apply_refund(refund, entity):
    order = Order.objects.select_for_update().get(pk=refund.intent.order_id)
    intent = PaymentIntent.objects.select_for_update().get(pk=refund.intent_id)
    refund = Refund.objects.select_for_update().get(pk=refund.pk)
    Razorpay.identifier(entity.get('id'), 'rfnd')
    if entity.get('payment_id') != intent.payment_id or type(entity.get('amount')) is not int or entity['amount'] != refund.amount:
        raise PaymentError('Refund details did not match the original payment.')
    if refund.provider_id and entity['id'] != refund.provider_id:
        raise PaymentError('Refund reference did not match.')
    refund.provider_id = entity['id']
    status = entity.get('status')
    if status not in ('pending', 'processed', 'failed'):
        raise PaymentError('Razorpay has not confirmed the refund status.')
    if refund.state != 'processed':
        refund.state = status
    if refund.state == 'processed':
        _full_refund(intent, order)
        intent.save()
    refund.save()
    return refund


def refresh_refund(refund):
    if refund.state in ('requested', 'submitting') and (timezone.now() - refund.updated_at).total_seconds() < 30:
        return refund
    if refund.state == 'requested':
        Refund.objects.filter(pk=refund.pk, state='requested').update(state='failed')
        return Refund.objects.get(pk=refund.pk)
    intent = refund.intent
    client = _client(intent)
    if refund.provider_id:
        return apply_refund(refund, client.refund_status(refund.provider_id))
    found = next((r for r in client.refunds(intent) if (r.get('notes') or {}).get('seer_refund') == refund.pk.hex), None)
    if found:
        return apply_refund(refund, found)
    # Unknown network outcomes are never retried as a fresh financial request.
    if refund.state in ('submitting', 'requested'):
        Refund.objects.filter(pk=refund.pk).update(state='uncertain')
    return Refund.objects.get(pk=refund.pk)


def ingest_event(connection, event_id, body):
    kind = body.get('event', '')
    if not isinstance(kind, str):
        raise PaymentError('Invalid payment event.')
    if PaymentEvent.objects.filter(mode=connection.mode, event_id=event_id).exists():
        return
    payload = body.get('payload', {})
    payment = payload.get('payment', {}).get('entity', {})
    order_entity = payload.get('order', {}).get('entity', {})
    refund_entity = payload.get('refund', {}).get('entity', {})
    if kind.startswith('refund.'):
        from django.db.models import Q
        match = Q(provider_id=refund_entity.get('id', 'not-found'))
        refund_key = (refund_entity.get('notes') or {}).get('seer_refund', '')
        if isinstance(refund_key, str) and re.fullmatch(r'[0-9a-f]{32}', refund_key):
            match |= Q(pk=refund_key)
        refund = Refund.objects.filter(match, intent__connection=connection).first()
        if refund:
            result = _client(refund.intent).refund_status(refund_entity['id'])
            apply_refund(refund, result)
        elif refund_entity.get('payment_id'):
            intent = PaymentIntent.objects.filter(connection=connection, payment_id=refund_entity['payment_id']).first()
            if intent:
                apply_payment(intent, _client(intent).payment(intent.payment_id))
    elif kind in ('payment.captured', 'payment.failed', 'order.paid'):
        provider_order = payment.get('order_id') or order_entity.get('id')
        intent = PaymentIntent.objects.filter(connection=connection, provider_order_id=provider_order).first() if provider_order else None
        if intent:
            if payment.get('id'):
                apply_payment(intent, _client(intent).payment(payment['id']))
            else:
                reconcile_payment(intent)
    PaymentEvent.objects.get_or_create(mode=connection.mode, event_id=event_id, defaults={'kind': kind[:60]})
