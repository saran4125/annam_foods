from datetime import date as date_cls, timedelta

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import Slot
from apps.catalog.services import resolve_menu, slot_is_open
from apps.content.models import Page
from apps.content.services import resolve_hero_slides, resolve_promo_tiles
from apps.delivery.services import normalise_pincode, zones_for_pincode

from . import services
from .cart import Cart

_ADD_MESSAGES = {
    services.PAUSED: "This kitchen isn’t accepting orders right now.",
    services.UNKNOWN_ITEM: "We can’t find that dish — it may have been removed.",
    services.CLOSED: "Ordering has closed for that meal time.",
    services.NOT_ON_MENU: "That dish isn’t on the menu for the time you chose.",
    services.CROSS_SLOT: "Your cart already holds a different meal and day. Start a fresh order to change it.",
    services.BAD_QUANTITY: "That quantity isn’t allowed.",
}


def _nav_pages():
    return Page.objects.filter(published=True, show_in_nav=True)


def _dates():
    today = timezone.localdate()
    return [(today, "Today"), (today + timedelta(days=1), "Tomorrow")]


def _parse_date(raw: str | None) -> date_cls:
    if not raw:
        return None
    try:
        return date_cls.fromisoformat(raw)
    except ValueError:
        return None


def _add_error_message(request, code):
    if code in _ADD_MESSAGES:
        messages.error(request, _ADD_MESSAGES[code])
        return True
    return False


def home(request):
    tenant = request.tenant
    today = timezone.localdate()
    slots = list(Slot.objects.filter(active=True))
    highlights = []
    for slot in slots:
        entries = resolve_menu(today, slot)[:3]
        if entries:
            highlights.append(
                {"slot": slot, "entries": entries, "open": slot_is_open(slot, today)}
            )

    # The honest urgency on a food site is the cutoff clock, not a fake
    # countdown. Surface the next one the customer can still order against.
    next_cutoff = next((h["slot"] for h in highlights if h["open"]), None)

    # A shop must still look like a shop after the final cutoff. Keep today's
    # dishes visible for browsing; the menu page remains the authority on
    # whether a line can actually be added. These are labelled "Featured",
    # never "Best sellers", because there is no sales ranking to back that up.
    featured = []
    for h in highlights:
        featured.extend(h["entries"])
    featured = featured[:8]
    return render(
        request,
        "storefront/home.html",
        {
            "hero_slides": resolve_hero_slides(),
            "promo_tiles": resolve_promo_tiles(),
            "highlights": highlights,
            "next_cutoff": next_cutoff,
            "featured": featured,
            "food_showcase": tenant.config.features.get("food_showcase", []),
            "pages": _nav_pages(),
            "cart": Cart(request),
        },
    )


def menu(request):
    tenant = request.tenant
    dates = _dates()

    raw_date = request.GET.get("date")
    chosen_date = dates[0][0]
    for d, _label in dates:
        if raw_date == d.isoformat():
            chosen_date = d

    slots = list(Slot.objects.filter(active=True))
    if not slots:
        return render(
            request, "storefront/menu.html",
            {"slots": [], "dates": dates, "chosen_date": chosen_date,
             "pages": _nav_pages(), "cart": Cart(request)},
        )

    slot_states = {s.key: slot_is_open(s, chosen_date) for s in slots}

    raw_slot = request.GET.get("slot")
    chosen_slot = next((s for s in slots if s.key == raw_slot), None)
    if chosen_slot is None:
        # Land on the next slot the customer can actually order from. Showing
        # a breakfast menu at 1pm is a closed door as a landing page.
        chosen_slot = next((s for s in slots if slot_states[s.key]), slots[0])

    entries = resolve_menu(chosen_date, chosen_slot)
    is_open = slot_is_open(chosen_slot, chosen_date)

    # Browsing the menu must never touch the cart (FIX-05): reading another
    # day or slot is not permission to delete what a customer has ordered.
    # Quantities are only shown when the cart is actually for this day/slot.
    cart = Cart(request)
    same_context = (
        cart.slot_key == chosen_slot.key and cart.delivery_date == chosen_date
    )

    return render(
        request,
        "storefront/menu.html",
        {
            "slots": slots,
            "dates": dates,
            "chosen_date": chosen_date,
            "chosen_slot": chosen_slot,
            "entries": entries,
            "slot_open": is_open,
            "slot_states": slot_states,
            "cart": cart,
            "cart_quantities": cart.items if same_context else {},
            "cart_mismatch": not cart.is_empty and not same_context,
            "pages": _nav_pages(),
        },
    )


@require_POST
def cart_add(request):
    if not request.tenant.can_take_orders:
        messages.error(request, "This kitchen isn’t accepting orders right now.")
        return redirect(services.safe_next(request, "storefront:menu"))
    cart = Cart(request)
    try:
        item_id = int(request.POST["item_id"])
        delta = int(request.POST.get("delta", 1))
    except (KeyError, ValueError):
        raise Http404
    slot_key = request.POST.get("slot_key")
    delivery_date = _parse_date(request.POST.get("delivery_date"))
    outcome = services.add_item(
        cart, request.tenant, item_id=item_id, delta=delta,
        slot_key=slot_key, delivery_date=delivery_date,
    )
    if outcome == services.OK:
        return redirect(services.safe_next(request, "storefront:cart"))
    _add_error_message(request, outcome)
    return redirect(services.safe_next(request, "storefront:menu"))


@require_POST
def cart_clear(request):
    """An explicit, user-initiated fresh order (`FIX-05`)."""
    Cart(request).clear()
    return redirect(services.safe_next(request, "storefront:menu"))


@require_POST
def cart_set_pincode(request):
    cart = Cart(request)
    raw = request.POST.get("pincode", "")
    pincode = normalise_pincode(raw)
    zones = zones_for_pincode(pincode, slot_key=cart.slot_key)

    if not zones:
        cart.set_pincode(pincode, None)
        messages.error(
            request,
            f"We don't deliver to {pincode or 'that pincode'} yet." if len(pincode) == 6
            else "That doesn't look like a 6-digit pincode.",
        )
    elif len(zones) == 1:
        cart.set_pincode(pincode, zones[0].id)
    else:
        zone_id = request.POST.get("zone_id")
        chosen = next((z for z in zones if str(z.id) == zone_id), None)
        cart.set_pincode(pincode, chosen.id if chosen else None)
    return redirect("storefront:cart")


def cart_detail(request):
    cart = Cart(request)
    totals = cart.totals()
    zones = zones_for_pincode(cart.pincode, slot_key=cart.slot_key) if cart.pincode else []
    slot = Slot.objects.filter(key=cart.slot_key).first() if cart.slot_key else None
    return render(
        request,
        "storefront/cart.html",
        {
            "cart": cart,
            "totals": totals,
            "zones": zones,
            "needs_area_choice": len(zones) > 1 and not cart.zone,
            "slot": slot,
            "slot_open": slot_is_open(slot, cart.delivery_date) if slot and cart.delivery_date else False,
            "pages": _nav_pages(),
        },
    )


def page_detail(request, slug):
    page = get_object_or_404(Page, slug=slug, published=True)
    return render(
        request,
        "storefront/page.html",
        {"page": page, "pages": _nav_pages(), "cart": Cart(request)},
    )