"""Serviceability. Checked before checkout, never after payment."""
import re

from .models import DeliveryZone

_DIGITS = re.compile(r"\D+")


def normalise_pincode(raw: str) -> str:
    """Customers type '600 106', '600-106' and 'pincode 600106'.

    Annam's bot already hit this — the original regex missed space-separated
    input and silently failed to match a perfectly valid pincode.
    """
    return _DIGITS.sub("", raw or "")


def zones_for_pincode(raw_pincode: str, slot_key: str | None = None):
    """Zones serving a pincode. Empty means we don't deliver there yet."""
    pincode = normalise_pincode(raw_pincode)
    if len(pincode) != 6:
        return []
    zones = list(DeliveryZone.objects.filter(pincode=pincode, active=True))
    if slot_key:
        zones = [z for z in zones if z.serves_slot(slot_key)]
    return zones


def is_serviceable(raw_pincode: str, slot_key: str | None = None) -> bool:
    return bool(zones_for_pincode(raw_pincode, slot_key))
