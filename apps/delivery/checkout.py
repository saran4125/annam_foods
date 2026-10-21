"""Explicit courier coverage and fees; no pincode-prefix guesses or free-shipping fallback."""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from apps.tenancy.models import TenantConfig
from .services import normalise_pincode


@dataclass(frozen=True)
class CourierQuote:
    area_name: str
    delivery_fee: Decimal
    min_order: Decimal
    id: None = None


def validate_checkout_settings(data):
    if not isinstance(data, dict):
        raise ValidationError('Invalid checkout settings.')
    pins = data.get('courier_pincodes', [])
    if not isinstance(pins, list) or len(pins) > 10000 or any(
            not isinstance(pin, str) or not re.fullmatch(r'[1-9][0-9]{5}', pin) for pin in pins):
        raise ValidationError('Enter approved six-digit Tamil Nadu pincodes, one per line.')
    if type(data.get('courier_enabled', False)) is not bool:
        raise ValidationError('Choose whether courier delivery is enabled.')
    for key in ('courier_fee', 'courier_minimum'):
        if data.get('courier_enabled') and key not in data:
            raise ValidationError('Set the courier charge and minimum before enabling courier delivery.')
        try:
            value = Decimal(str(data.get(key, '0')))
            if not value.is_finite() or value < 0 or value > Decimal('99999.99') or value.as_tuple().exponent < -2:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError('Delivery fees and minimums must be valid non-negative amounts.')
    dates = data.get('closed_dates', [])
    from datetime import date
    try:
        if not isinstance(dates, list) or len(dates) > 366:
            raise ValueError
        for day in dates:
            date.fromisoformat(day)
    except (ValueError, TypeError):
        raise ValidationError('Enter closed meal dates as YYYY-MM-DD, one per line.')
    if data.get('courier_enabled') and not pins:
        raise ValidationError('Add approved Tamil Nadu pincodes before enabling courier delivery.')
    if not isinstance(data.get('payment_instructions', ''), str) or len(data.get('payment_instructions', '')) > 1000:
        raise ValidationError('Payment instructions must be at most 1,000 characters.')
    return data


@transaction.atomic
def save_checkout_settings(tenant, data):
    validate_checkout_settings(data)
    config = TenantConfig.objects.select_for_update().get(tenant=tenant)
    config.checkout_settings = data
    config.save(update_fields=['checkout_settings'])


def courier_quote(tenant, pincode):
    settings = tenant.config.checkout_settings or {}
    try:
        validate_checkout_settings(settings)
    except ValidationError:
        return None
    pin = normalise_pincode(pincode)
    if not settings.get('courier_enabled') or pin not in settings.get('courier_pincodes', []):
        return None
    return CourierQuote('Tamil Nadu courier delivery', Decimal(str(settings.get('courier_fee', '0'))),
                        Decimal(str(settings.get('courier_minimum', '0'))))
