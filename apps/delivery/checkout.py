"""Tamil Nadu shop delivery charges, independent of meal pincode coverage."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from apps.tenancy.models import TenantConfig


@dataclass(frozen=True)
class CourierQuote:
    area_name: str
    delivery_fee: Decimal
    min_order: Decimal
    id: None = None


def validate_checkout_settings(data):
    if not isinstance(data, dict):
        raise ValidationError('Invalid checkout settings.')
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
    if not isinstance(data.get('payment_instructions', ''), str) or len(data.get('payment_instructions', '')) > 1000:
        raise ValidationError('Payment instructions must be at most 1,000 characters.')
    return data


@transaction.atomic
def save_checkout_settings(tenant, data):
    validate_checkout_settings(data)
    config = TenantConfig.objects.select_for_update().get(tenant=tenant)
    config.checkout_settings = data
    config.save(update_fields=['checkout_settings'])


def courier_quote(tenant, pincode=""):
    # Legacy callers may pass a postal code; it is no longer a coverage whitelist.
    settings = tenant.config.checkout_settings or {}
    try:
        validate_checkout_settings(settings)
    except ValidationError:
        return None
    if not settings.get('courier_enabled'):
        return None
    return CourierQuote('Tamil Nadu courier delivery', Decimal(str(settings.get('courier_fee', '0'))),
                        Decimal(str(settings.get('courier_minimum', '0'))))
