"""Guest checkout: live validation, explicit delivery coverage and one order per review."""
import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing.pricing import checkout_totals
from apps.catalog.models import Slot
from apps.catalog.services import slot_is_open
from apps.delivery.checkout import courier_quote, validate_checkout_settings
from apps.delivery.services import zones_for_pincode
from apps.orders.models import Channel, Order, PaymentMode
from apps.orders.services import (OrderError, RequestedLine, create_order, get_or_create_customer,
                                  price_lines, price_courier_lines)
from apps.tenancy.models import TenantConfig

SALT = 'storefront.checkout.v1'


def browser_key(request, create=True):
    key = 'checkout.browser.' + str(request.tenant.pk)
    value = request.session.get(key)
    if not value and create:
        value = uuid.uuid4().hex
        request.session[key] = value
    return value


def checkout_quote(tenant, cart, details, *, now=None):
    if not tenant.can_take_orders or not tenant.feature('website_ordering'):
        raise OrderError('This kitchen is not accepting website orders right now.')
    from apps.payments.services import payment_choices, active_connection, _paise
    from apps.payments.provider import PaymentError
    choices = payment_choices(tenant)
    method = details.get('payment_method') or ('manual' if tenant.feature('manual_payments') else 'online')
    if method not in dict(choices):
        raise OrderError('The selected payment method is not available. Please choose another payment method.')
    try:
        validate_checkout_settings(tenant.config.checkout_settings or {})
    except ValidationError:
        raise OrderError('Delivery settings are not ready. Please contact the kitchen.')
    requested = [RequestedLine(int(pk), qty) for pk, qty in cart.items.items()]
    slot = None
    now = now or timezone.localtime()
    if cart.is_courier:
        if not tenant.feature('snacks_courier'):
            raise OrderError('Shop ordering is not available.')
        lines, subtotal = price_courier_lines(requested)
        zone = courier_quote(tenant, details['pincode'])
        if zone is None:
            raise OrderError("We don't ship shop items to this pincode. Orders are accepted only for approved Tamil Nadu pincodes.")
    else:
        slot = Slot.objects.filter(key=cart.slot_key, active=True).first()
        if not slot or cart.delivery_date not in (now.date(), now.date() + timedelta(days=1)):
            raise OrderError('Choose today or tomorrow and an available meal from the menu.')
        if not slot_is_open(slot, cart.delivery_date, now=now):
            raise OrderError('Ordering has closed for this meal. Choose another meal or date.')
        if cart.delivery_date.isoformat() in (tenant.config.checkout_settings or {}).get('closed_dates', []):
            raise OrderError('The kitchen is closed on this date. Please choose another date.')
        closed = tenant.config.kitchen_closed_window or {}
        if closed.get('from') and closed.get('to') and closed['from'] <= cart.delivery_date.isoformat() <= closed['to']:
            raise OrderError('The kitchen is closed on this date. Please choose another date.')
        lines, subtotal = price_lines(requested, delivery_date=cart.delivery_date, slot=slot)
        zones = zones_for_pincode(details['pincode'], slot.key)
        if not zones:
            raise OrderError("We don't deliver meals to this pincode.")
        zone = next((z for z in zones if str(z.pk) == str(details.get('zone_id'))), None)
        if zone is None:
            if len(zones) != 1:
                raise OrderError('Choose your delivery area, then review your order again.')
            zone = zones[0]
    if subtotal < zone.min_order:
        raise OrderError(f'This delivery requires an items subtotal of ₹{zone.min_order:.2f}. Add ₹{zone.min_order - subtotal:.2f} more.')
    amounts = checkout_totals(tenant, lines, zone.delivery_fee)
    connection = active_connection() if method == 'online' else None
    if connection:
        try:
            _paise(amounts['total'])
        except PaymentError as exc:
            raise OrderError(str(exc))
    return {**amounts, 'online_mode': connection.mode if connection else '',
            'online_key_id': connection.key_id if connection else '', 'lines': lines, 'zone': zone, 'slot': slot,
            'delivery_date': cart.delivery_date if slot else None,
            'minimum': zone.min_order, 'kind': 'courier' if cart.is_courier else 'scheduled'}


def fingerprint(quote, details):
    data = {'details': details, 'lines': quote['lines'], 'total': str(quote['total']),
            'fee': str(quote['delivery_fee']), 'date': str(quote['delivery_date']),
            'slot': quote['slot'].pk if quote['slot'] else None, 'kind': quote['kind'],
            'online_mode': quote['online_mode'], 'online_key_id': quote['online_key_id'],
            'pricing': quote['pricing'], 'area': quote['zone'].area_name, 'minimum': str(quote['minimum'])}
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def review_token(request, quote, details):
    return signing.dumps({'tenant': request.tenant.pk, 'browser': browser_key(request),
                          'ref': uuid.uuid4().hex, 'fingerprint': fingerprint(quote, details)}, salt=SALT)


def read_token(request, token):
    try:
        data = signing.loads(token, salt=SALT, max_age=1800)
        if data['tenant'] != request.tenant.pk or data['browser'] != browser_key(request, create=False):
            raise ValueError
        uuid.UUID(data['ref'])
        return data
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        raise OrderError('Your order review expired or changed. Please review the order again.')


def external_ref(data):
    return f"web:{data['browser']}:{data['ref']}"


@transaction.atomic
def place_checkout(request, cart, details, token):
    data = read_token(request, token)
    # Serialize submissions for this kitchen. The unique order reference is an
    # additional database guard; refreshes never create a second order.
    config = TenantConfig.objects.select_for_update().get(tenant=request.tenant)
    request.tenant.config = config
    existing = Order.objects.filter(external_ref=external_ref(data)).first()
    if existing:
        return existing, data['ref'], False
    quote = checkout_quote(request.tenant, cart, details)
    if fingerprint(quote, details) != data['fingerprint']:
        raise OrderError('Your cart, delivery details or prices changed. Review the updated total before placing the order.')
    customer = get_or_create_customer(request.tenant, phone=details['phone'], name=details['name'],
                                       email=details.get('email', ''), channel=Channel.WEB)
    snapshot = {key: details.get(key, '') for key in ('line1', 'line2', 'landmark', 'pincode', 'city')}
    snapshot.update(area=quote['zone'].area_name, state='Tamil Nadu', state_code='33',
                    recipient_name=details['name'], phone=details['phone'], email=details.get('email', ''))
    order = create_order(request.tenant, customer=customer,
        requested=[RequestedLine(int(pk), qty) for pk, qty in cart.items.items()],
        slot=quote['slot'], delivery_date=quote['delivery_date'], address_snapshot=snapshot,
        channel=Channel.WEB, payment_mode=details.get('payment_method') or PaymentMode.MANUAL,
        external_ref=external_ref(data), website_checkout=True)
    if order.total != quote['total'] or order.items != quote['lines']:
        raise OrderError('Prices changed while placing your order. Please review again.')
    if order.payment_mode == 'online':
        from apps.payments.models import PaymentIntent, RazorpayConnection
        connection = RazorpayConnection.objects.get(enabled=True, mode=quote['online_mode'], key_id=quote['online_key_id'])
        PaymentIntent.objects.create(order=order, connection=connection, mode=connection.mode,
            key_id=connection.key_id, amount=int(order.total * 100))
    return order, data['ref'], True
