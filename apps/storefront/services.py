"""Purchase rules shared by every adding surface.

The web cart, and later the WhatsApp flow, validate an order the same way —
never partly in a view and partly in a template. This is where availability,
eligibility and quantity live; views just translate the result into a message.
"""
from datetime import date as date_cls
from urllib.parse import urlparse

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.catalog.models import MenuItem, Slot
from apps.catalog.services import resolve_menu, customer_slot_is_open

from .cart import MAX_LINE_QUANTITY

# Typed outcomes a view can turn into a visible message.
OK = None
PAUSED = "paused"
UNKNOWN_ITEM = "unknown_item"
CLOSED = "closed"
NOT_ON_MENU = "not_on_menu"
SOLD_OUT = "sold_out"
CROSS_SLOT = "cross_slot"
CROSS_KIND = "cross_kind"
BAD_QUANTITY = "bad_quantity"

MAX_DELTA = 10  # one click adds or removes a bounded handful, not a flood


def safe_next(request, default: str) -> str:
    """A redirect target that can't point a customer off our site (`FIX-07`).

    Absolute external URLs, protocol-relative URLs and unsafe schemes are all
    rejected; the caller then falls back to a known-good local route.
    """
    proposed = request.POST.get("next", "")
    if not proposed:
        return reverse(default)
    if not url_has_allowed_host_and_scheme(
        proposed, allowed_hosts={request.get_host()}, require_https=False
    ):
        return reverse(default)
    parsed = urlparse(proposed)
    if parsed.scheme or parsed.netloc:
        return reverse(default)
    if not proposed.startswith("/"):
        return reverse(default)
    return proposed


def _bounded_delta(delta) -> bool:
    return isinstance(delta, int) and -MAX_DELTA <= delta <= MAX_DELTA and delta != 0


def add_item(cart, tenant, *, item_id: int, delta: int, slot_key: str,
             delivery_date: date_cls | None):
    """Add or remove one line, validating it against the live menu.

    Returns one of the OK / error codes above. This is the single decision
    point for "can this go in the cart" — availability, slot openness, cross-slot
    mixing and quantity bounds all close here, not in the template.
    """
    if not tenant.can_take_orders:
        return PAUSED
    if not _bounded_delta(delta):
        return BAD_QUANTITY
    if slot_key is None or delivery_date is None:
        return UNKNOWN_ITEM
    slot = Slot.objects.filter(key=slot_key,active=True).first()
    item = MenuItem.objects.filter(pk=item_id).first()
    if slot is None or item is None:
        return UNKNOWN_ITEM
    from apps.delivery.policies import validate_combination, restriction_message
    from apps.orders.services import OrderError
    if not cart.is_empty:
        if cart.delivery_date and cart.delivery_date != delivery_date:
            return CROSS_SLOT
        try:
            validate_combination(set(cart.slot_keys)|{slot_key})
        except OrderError as exc:
            return str(exc)
        if cart.pincode:
            message = restriction_message(cart.pincode,set(cart.slot_keys)|{slot_key},area_id=cart.zone_id)
            if message:
                return message
    if delta > 0:
        if cart.pincode:
            message=restriction_message(cart.pincode,set(cart.slot_keys)|{slot_key},area_id=cart.zone_id)
            if message:
                return message
        if not customer_slot_is_open(slot, delivery_date):
            return CLOSED
        entry = next(
            (e for e in resolve_menu(delivery_date, slot) if e.item.id == item_id),
            None,
        )
        # resolve_menu only returns orderable entries, so a found entry is
        # available and not sold out; anything else is simply not on the menu.
        if entry is None:
            return NOT_ON_MENU

    current = cart.items.get(cart.item_key(item_id,slot_key), 0)
    after = current + delta
    if after < 0 or after > MAX_LINE_QUANTITY:
        return BAD_QUANTITY

    if not cart.slot_key or cart.is_courier or cart.is_empty:
        cart.set_context(slot_key,delivery_date)
    cart.add(item_id,delta,slot_key)
    return OK


def add_courier_item(cart, tenant, *, item_id: int, delta: int):
    """Add or remove one shop (courier) item.

    Courier goods have no slot or delivery day; they are on sale while the
    item is active. A shop item never joins a meal cart, or the reverse.
    """
    if not tenant.can_take_orders:
        return PAUSED
    if not _bounded_delta(delta):
        return BAD_QUANTITY
    item = MenuItem.objects.filter(pk=item_id, fulfilment="courier").first()
    if item is None:
        return UNKNOWN_ITEM
    if delta > 0 and not item.active:
        return NOT_ON_MENU
    from apps.delivery.policies import validate_combination, restriction_message
    from apps.orders.services import OrderError
    try:
        if not cart.is_empty:
            validate_combination(set(cart.slot_keys)|{'snacks'})
            if cart.pincode and not cart.is_courier:
                message = restriction_message(cart.pincode,set(cart.slot_keys)|{'snacks'},area_id=cart.zone_id)
                if message:
                    return message
    except OrderError as exc:
        return str(exc)
    if cart.is_empty:
        cart.set_courier()
    current = cart.items.get(str(item_id), 0)
    after = current + delta
    if after < 0 or after > MAX_LINE_QUANTITY:
        return BAD_QUANTITY

    cart.add(item_id, delta, "snacks")
    return OK
