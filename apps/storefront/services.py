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
from apps.catalog.services import resolve_menu, slot_is_open

from .cart import MAX_LINE_QUANTITY

# Typed outcomes a view can turn into a visible message.
OK = None
PAUSED = "paused"
UNKNOWN_ITEM = "unknown_item"
CLOSED = "closed"
NOT_ON_MENU = "not_on_menu"
SOLD_OUT = "sold_out"
CROSS_SLOT = "cross_slot"
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

    slot = Slot.objects.filter(key=slot_key).first()
    if slot is None:
        return UNKNOWN_ITEM

    item = MenuItem.objects.filter(pk=item_id).first()
    if item is None:
        return UNKNOWN_ITEM

    # A dinner item must not be dropped into a lunch order, and vice versa.
    # Switching means walking away from the current cart's context.
    if cart.slot_key and cart.delivery_date:
        if cart.slot_key != slot_key or cart.delivery_date != delivery_date:
            if not cart.is_empty:
                return CROSS_SLOT
            cart.set_context(slot_key, delivery_date)
    elif not cart.slot_key:
        cart.set_context(slot_key, delivery_date)

    if delta > 0:
        if not slot_is_open(slot, delivery_date):
            return CLOSED
        entry = next(
            (e for e in resolve_menu(delivery_date, slot) if e.item.id == item_id),
            None,
        )
        # resolve_menu only returns orderable entries, so a found entry is
        # available and not sold out; anything else is simply not on the menu.
        if entry is None:
            return NOT_ON_MENU

    current = cart.items.get(str(item_id), 0)
    after = current + delta
    if after < 0 or after > MAX_LINE_QUANTITY:
        return BAD_QUANTITY

    cart.add(item_id, delta)
    return OK