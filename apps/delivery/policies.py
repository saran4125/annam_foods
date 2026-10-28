"""Pincode/area rules shared by checkout, staff orders and future integrations."""
from decimal import Decimal
from dataclasses import dataclass
from .services import zones_for_pincode

DINNER_MESSAGE = 'Dinner cannot be combined with other food categories. Please place a separate order for Dinner.'
BREAKFAST_MESSAGE = 'Breakfast delivery is not available for your pincode.'
BREAKFAST_DINNER_MESSAGE = 'Breakfast and Dinner delivery services are not available for your pincode.'
SNACKS_ONLY_MESSAGE = 'Only Snacks delivery is available for your pincode. Breakfast, Lunch, and Dinner delivery services are not available.'
COURIER_NOTICE = 'Please note that courier charges are not included in the current order amount. The applicable courier charges will be confirmed after your order has been dispatched, and you will be required to pay the courier charges separately after dispatch.'


def validate_combination(keys):
    from apps.orders.services import OrderError
    keys = set(keys)
    if 'dinner' in keys and keys != {'dinner'}:
        raise OrderError(DINNER_MESSAGE)


def restriction_message(pincode, keys, *, area_id=None):
    zones = zones_for_pincode(pincode)
    if area_id:
        zones = [z for z in zones if str(z.pk) == str(area_id)]
    if not zones:
        return "We don't deliver meals to this pincode."
    allowed = set().union(*(set(z.slot_keys) if z.slot_keys else {'breakfast','lunch','dinner','snacks'} for z in zones))
    missing = set(keys) - allowed
    if not missing:
        return ''
    if allowed == {'snacks'}:
        return SNACKS_ONLY_MESSAGE
    if not {'breakfast','dinner'} & allowed and missing & {'breakfast','dinner'}:
        return BREAKFAST_DINNER_MESSAGE
    if 'breakfast' in missing:
        return BREAKFAST_MESSAGE
    return 'Dinner delivery is not available for your pincode.' if 'dinner' in missing else 'This food category is not available for your pincode.'


def eligible_zones(pincode, keys):
    return [z for z in zones_for_pincode(pincode) if all(z.serves_slot(key) for key in keys)]


def select_zone(pincode, keys, *, zone_id=None, area_name=None):
    from apps.orders.services import OrderError
    validate_combination(keys)
    message = restriction_message(pincode, keys, area_id=zone_id)
    if message:
        raise OrderError(message)
    zones = eligible_zones(pincode, keys)
    if zone_id:
        zone = next((z for z in zones if str(z.pk)==str(zone_id)), None)
    elif area_name:
        zone = next((z for z in zones if z.area_name==area_name), None)
    else:
        zone = zones[0] if len(zones)==1 else None
    if zone is None:
        raise OrderError('Choose your delivery area, then review your order again.')
    return zone


@dataclass(frozen=True)
class DeferredCourierQuote:
    area_name: str = 'Courier delivery — charge payable after dispatch'
    delivery_fee: Decimal = Decimal('0')
    min_order: Decimal = Decimal('0')
    id: None = None
    deferred: bool = True


def snacks_delivery_quote(tenant, details):
    from apps.orders.services import OrderError
    config = tenant.config.checkout_settings or {}
    from django.core.exceptions import ValidationError
    from .checkout import validate_checkout_settings
    try:
        validate_checkout_settings(config)
    except ValidationError:
        raise OrderError('Delivery settings are not ready. Please contact the kitchen.')
    if not config.get('courier_enabled'):
        raise OrderError('Shop delivery is currently unavailable. Please contact the kitchen.')
    country = (details.get('country') or 'India').strip()
    pin = details.get('pincode', '')
    if country.casefold() == 'india' and zones_for_pincode(pin):
        return select_zone(pin, ['snacks'], zone_id=details.get('zone_id'), area_name=details.get('area'))
    if country.casefold() == 'india' and (details.get('city') or '').strip().casefold() in {'chennai','madras'}:
        raise OrderError('Enter an approved Chennai delivery pincode and choose your area.')
    return DeferredCourierQuote(min_order=Decimal(str(config.get('courier_minimum','0'))))
