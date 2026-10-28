"""Deferred courier receivables and held WhatsApp drafts; no provider calls."""
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
from apps.messaging.services import queue
from apps.messaging.payloads import text, template
from apps.messaging.models import MessageStatus, OutboundMessage, WhatsAppMessage
from .models import Order, CourierCharge, OrderEvent, OrderStatus
from .services import OrderError
from apps.delivery.policies import COURIER_NOTICE


def team_phone(tenant,order):
    settings=tenant.config.checkout_settings or {}
    return (settings.get('courier_team_phone') or tenant.config.support_phone or
            OutboundMessage.objects.filter(dedupe_key=f'courier:{order.pk}:disclosure:team').values_list('to_phone',flat=True).first())


def notice(tenant, order, body, key):
    settings = tenant.config.checkout_settings or {}
    enabled = settings.get('courier_notifications_enabled',False)
    recipients = [('customer', order.buyer_phone),('team',team_phone(tenant,order))]
    for role, phone in recipients:
        if not phone:
            continue
        # Held rows are never selected by the sender while WhatsApp is offline.
        import re
        phone=re.sub(r'\D','',phone)
        payload=text(f'Order {order.order_no}\n{body}')
        if enabled:
            name=settings.get(f'courier_{role}_template')
            if not name:
                raise OrderError('Configure approved customer and team WhatsApp templates before enabling courier notifications.')
            payload=template(name,settings.get('courier_template_language') or 'en',params=[order.order_no,body])
        message = queue(tenant,phone,payload,purpose='courier_'+role,dedupe_key=f'courier:{order.pk}:{key}:{role}')
        if not enabled and message.status == MessageStatus.PENDING:
            message.status=MessageStatus.HELD
            message.save(update_fields=['status'])
            WhatsAppMessage.objects.filter(outbound=message).update(status='held')


@transaction.atomic
def prepare_courier_charge(order):
    if not team_phone(order.tenant,order):
        raise OrderError('Configure the team WhatsApp phone in Checkout settings before accepting courier orders.')
    charge,_=CourierCharge.objects.get_or_create(order=order)
    notice(order.tenant,order,COURIER_NOTICE,'disclosure')
    return charge


@transaction.atomic
def record_dispatch(order, *, amount, courier_name, tracking_number, actor):
    order=Order.objects.select_for_update().get(pk=order.pk)
    if not order.address.get('courier_deferred'):
        raise OrderError('This order does not use post-dispatch courier charging.')
    if order.status not in (OrderStatus.OUT_FOR_DELIVERY,OrderStatus.DELIVERED):
        raise OrderError('Mark the order dispatched / out for delivery before confirming courier charges.')
    try:
        amount=Decimal(str(amount))
        if not amount.is_finite() or amount<0 or amount>Decimal('99999999.99') or amount.as_tuple().exponent < -2:
            raise InvalidOperation
    except (InvalidOperation,ValueError,TypeError):
        raise OrderError('Enter a valid non-negative courier amount with at most two decimal places.')
    charge=CourierCharge.objects.select_for_update().get(order=order)
    if charge.dispatched_at:
        if charge.amount==amount and charge.tracking_number==tracking_number:
            return charge
        raise OrderError('The confirmed courier charge cannot be overwritten. Record a correction separately with the customer.')
    if not courier_name.strip() or not tracking_number.strip():
        raise OrderError('Enter the courier service and tracking number.')
    charge.amount=amount;charge.courier_name=courier_name[:120];charge.tracking_number=tracking_number[:120];charge.dispatched_at=timezone.now();charge.save()
    notice(order.tenant,order,f'Your Snacks order has been dispatched via {charge.courier_name}. Tracking: {charge.tracking_number}. Courier charge payable separately: ₹{amount:.2f}. This is in addition to your food order payment.','dispatch')
    OrderEvent.objects.create(order=order,from_status=order.status,to_status=order.status,actor=actor[:60],note=f'Courier charge confirmed: ₹{amount:.2f}; {tracking_number}'[:200])
    return charge


@transaction.atomic
def confirm_courier_payment(order, *, reference, actor):
    order=Order.objects.select_for_update().get(pk=order.pk)
    charge=CourierCharge.objects.select_for_update().get(order=order)
    if actor != 'razorpay' and charge.online_payments.filter(mode='live',state__in=['ready','creating','uncertain']).exists():
        raise OrderError('An online courier payment is pending. Verify it before recording a manual payment.')
    if not charge.dispatched_at or charge.amount is None:
        raise OrderError('Confirm the dispatched courier amount first.')
    if not charge.paid_at:
        charge.paid_at=timezone.now();charge.payment_reference=reference[:120];charge.save()
        notice(order.tenant,order,f'Courier payment received: ₹{charge.amount:.2f}. Reference: {reference or "manually confirmed"}.','paid')
        OrderEvent.objects.create(order=order,from_status=order.status,to_status=order.status,actor=actor[:60],note=f'Courier payment received: ₹{charge.amount:.2f}')
    return charge


@transaction.atomic
def release_courier_drafts(tenant):
    if not (tenant.config.checkout_settings or {}).get('courier_notifications_enabled'):
        raise OrderError('Enable courier WhatsApp notifications only after configuring and verifying the messaging provider.')
    settings=tenant.config.checkout_settings or {}
    if not settings.get('courier_customer_template') or not settings.get('courier_team_template'):
        raise OrderError('Both approved courier WhatsApp templates are required before release.')
    count=0
    for message in OutboundMessage.objects.select_for_update().filter(status=MessageStatus.HELD,purpose__in=['courier_customer','courier_team']):
        role=message.purpose.removeprefix('courier_')
        order=Order.objects.get(pk=int(message.dedupe_key.split(':')[1]))
        body=message.payload.get('body','').partition('\n')[2]
        message.payload=template(settings['courier_'+role+'_template'],settings.get('courier_template_language') or 'en',params=[order.order_no,body])
        message.status=MessageStatus.PENDING;message.save(update_fields=['status','payload']);WhatsAppMessage.objects.filter(outbound=message).update(status='queued');count+=1
    return count
