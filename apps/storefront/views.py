import logging
from datetime import date as date_cls, timedelta

from django.contrib import messages
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import MenuCategory, MenuItem, Slot
from apps.catalog.services import (
    SHOP_SORTS, category_family_ids, resolve_menu, search_shop, shop_categories,
    shop_items, slot_is_open,
)
from apps.content.models import Page
from apps.content.services import resolve_hero_slides, resolve_promo_tiles
from apps.delivery.models import DeliveryZone
from apps.delivery.services import normalise_pincode, zones_for_pincode

from . import services
from .cart import Cart

_ADD_MESSAGES = {
    services.PAUSED: "This kitchen isn’t accepting orders right now.",
    services.UNKNOWN_ITEM: "We can’t find that dish — it may have been removed.",
    services.CLOSED: "Ordering has closed for that meal time.",
    services.NOT_ON_MENU: "That dish isn’t on the menu for the time you chose.",
    services.CROSS_SLOT: "Your cart already holds a different meal and day. Start a fresh order to change it.",
    services.CROSS_KIND: "Meals and shop items are delivered separately. Finish or clear your current cart first.",
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


def _shop_enabled(tenant) -> bool:
    return tenant.feature("snacks_courier")


def _split_home_sections(sections):
    """TenantConfig.home_sections holds category tiles plus, optionally, one
    `kind: spotlight` feature block and one `kind: hero` text block (edited in
    the owner backend). Plain entries are tiles."""
    tiles, spotlight, hero = [], None, {}
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        if section.get("kind") == "spotlight":
            spotlight = spotlight or section
        elif section.get("kind") == "hero":
            hero = hero or section
        else:
            tiles.append(section)
    return tiles, spotlight, hero


def home(request):
    from apps.content.services import storefront_appearance
    appearance = storefront_appearance(request)
    design = appearance["storefront_design"]
    tenant = request.tenant
    today = timezone.localdate()
    slots = list(Slot.objects.filter(active=True))
    highlights = []
    for slot in slots:
        entries = resolve_menu(today, slot)[:6]  # the menu board lists up to six per meal
        if entries:
            highlights.append(
                {"slot": slot, "entries": entries, "open": slot_is_open(slot, today)}
            )

    # The honest urgency on a food site is the cutoff clock, not a fake
    # countdown. Surface the next one the customer can still order against.
    next_cutoff = next((h["slot"] for h in highlights if h["open"]), None)
    # The menu board opens on the meal a customer can still order.
    board_default = next_cutoff.key if next_cutoff else (highlights[0]["slot"].key if highlights else "")

    # A shop must still look like a shop after the final cutoff. Keep today's
    # dishes visible for browsing; the menu page remains the authority on
    # whether a line can actually be added. These are labelled "Featured",
    # never "Best sellers", because there is no sales ranking to back that up.
    featured = []
    for h in highlights:
        featured.extend(h["entries"])
    featured = featured[:8]

    # Annam-style kitchens also sell shipped goods. Surface the shelves and a
    # few popular lines; both disappear when the kitchen has no shop.
    shelves, popular = [], []
    if _shop_enabled(tenant):
        shelves = shop_categories()
        items = list(shop_items().order_by("category__sort", "sort", "name")[:60])
        items.sort(key=lambda i: not i.image)  # photographed goods first; stable otherwise
        # Owner-tagged favourites first, topped up from the catalog to a full row.
        picked = [i for i in items if "featured" in (i.tags or [])][:12]
        popular = picked + [i for i in items if i not in picked][:12 - len(picked)]  # 12 fills 2, 3, 4 or 6 columns
    tiles, spotlight, hero = _split_home_sections(tenant.config.home_sections)
    if spotlight or design.get('content', {}).get('spotlight.title') or design.get('images', {}).get('spotlight'):
        spotlight = dict(spotlight or {'title': appearance['storefront_copy']['spotlight.title'], 'link': reverse('storefront:menu')})
        spotlight['points'] = [line.strip() for line in appearance['storefront_copy']['spotlight.points'].splitlines() if line.strip()][:30]
    hero_slides = resolve_hero_slides()
    if not hero_slides and design.get('images', {}).get('offers'):
        from types import SimpleNamespace
        hero_slides = [SimpleNamespace(id=0, title=appearance['storefront_copy']['offers.title'],
            subtitle=appearance['storefront_copy']['offers.body'], link=reverse('storefront:menu'),
            image=SimpleNamespace(url=design['images']['offers']))]

    # The hero's plate and side dishes: photographed meals first (they look
    # like a meal), then the shop's popular lines.
    hero_picks, seen = [], set()
    for item in [e.item for h in highlights for e in h["entries"]] + popular:
        if item.image and item.image.name not in seen:  # same photo twice (Idly at two meals) reads as a bug
            hero_picks.append(item)
            seen.add(item.image.name)
    hero_picks = hero_picks[:4]
    numbers = []
    if shelves or highlights:
        numbers = [  # (count, label, sub-line, icon)
            (sum(c.item_count for c in shelves), "Pantry products", "made in our kitchen", "bag"),
            (MenuItem.objects.filter(active=True, fulfilment="scheduled").count(), "Daily dishes", "breakfast to dinner", "clock"),
            (len(shelves), "Categories", "podis to pickles", "leaf"),
            (DeliveryZone.objects.filter(active=True).count(), "Delivery areas", "and growing", "pin"),
        ]
        numbers = [row for row in numbers if row[0]]

    # Slot cards wear the first photographed dish as their cover.
    for h in highlights:
        h["cover"] = next((e.item.image for e in h["entries"] if e.item.image), None)
    cart = Cart(request)
    response = render(
        request,
        "storefront/home.html",
        {
            "hero_slides": hero_slides,
            "promo_tiles": resolve_promo_tiles(),
            "highlights": highlights,
            "next_cutoff": next_cutoff,
            "featured": featured,
            "food_showcase": tiles,
            "spotlight": spotlight,
            "shelves": shelves,
            "popular": popular,
            "hero": hero,
            "hero_picks": hero_picks,
            "board_default": board_default,
            "tomorrow": today + timedelta(days=1),
            "numbers": numbers,
            "shop_enabled": _shop_enabled(tenant),
            "ordering_enabled": tenant.feature("website_ordering"),
            "pages": _nav_pages(),
            "cart": cart,
            "cart_quantities": cart.items if cart.is_courier else {},
        },
    )
    if getattr(request, "_storefront_appearance", {}).get("appearance_preview"):
        from django.utils.cache import patch_cache_control
        patch_cache_control(response, private=True, no_store=True)
        response["X-Robots-Tag"] = "noindex, nofollow"
    return response


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
             "pages": _nav_pages(), "cart": Cart(request),
             "ordering_enabled": tenant.feature("website_ordering")},
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
            "ordering_enabled": tenant.feature("website_ordering"),
        },
    )


@require_POST
def cart_add(request):
    if not request.tenant.feature("website_ordering"):
        raise Http404
    if not request.tenant.can_take_orders:
        messages.error(request, "This kitchen isn’t accepting orders right now.")
        return redirect(services.safe_next(request, "storefront:menu"))
    cart = Cart(request)
    try:
        item_id = int(request.POST["item_id"])
        delta = int(request.POST.get("delta", 1))
    except (KeyError, ValueError):
        raise Http404
    if request.POST.get("kind") == "shop":
        if not _shop_enabled(request.tenant):
            raise Http404
        outcome = services.add_courier_item(cart, request.tenant, item_id=item_id, delta=delta)
        if outcome == services.OK:
            return redirect(services.safe_next(request, "storefront:cart"))
        _add_error_message(request, outcome)
        return redirect(services.safe_next(request, "storefront:shop"))
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
            "ordering_enabled": request.tenant.feature("website_ordering"),
            "slot_open": cart.is_courier or (slot_is_open(slot, cart.delivery_date) if slot and cart.delivery_date else False),
            "pages": _nav_pages(),
        },
    )


def _about_context(tenant):
    """Photos and numbers for the About page, read from the live catalog."""
    picks, seen_shelves = [], set()
    if _shop_enabled(tenant):
        for item in shop_items().exclude(image="").order_by("category__sort", "sort", "name"):
            if item.category_id not in seen_shelves:
                seen_shelves.add(item.category_id)
                picks.append(item)
            if len(picks) >= 8:
                break
    meals, seen_photos = [], set()
    for item in MenuItem.objects.filter(active=True, fulfilment="scheduled").exclude(image=""):
        if item.image.name not in seen_photos:
            seen_photos.add(item.image.name)
            meals.append(item)
        if len(meals) >= 4:
            break
    shelves = shop_categories() if _shop_enabled(tenant) else []
    stats = [
        (sum(c.item_count for c in shelves), "Pantry products", "made in our kitchen", "bag"),
        (MenuItem.objects.filter(active=True, fulfilment="scheduled").count(), "Daily dishes", "breakfast to dinner", "clock"),
        (len(shelves), "Categories", "podis to pickles", "leaf"),
        (DeliveryZone.objects.filter(active=True).count(), "Delivery areas", "and growing", "pin"),
    ]
    return {
        "gallery": picks, "meals": meals, "numbers": [r for r in stats if r[0]],
        "hero_picks": (meals[:1] + picks[:2])[:3], "slots": list(Slot.objects.filter(active=True)),
    }


def about(request):
    """The premium About page. Its story text is the owner's `about` page, so
    it stays editable in the owner backend; everything else reads live data."""
    page = Page.objects.filter(slug="about", published=True).first()
    return render(
        request, "storefront/about.html",
        {"page": page, "pages": _nav_pages(), "cart": Cart(request), **_about_context(request.tenant)},
    )


def page_detail(request, slug):
    if slug == "about":
        return about(request)
    page = get_object_or_404(Page, slug=slug, published=True)
    return render(
        request,
        "storefront/page.html",
        {"page": page, "pages": _nav_pages(), "cart": Cart(request)},
    )


def shop(request, slug=None):
    """The shop: courier goods by shelf, with search and sort."""
    tenant = request.tenant
    if not _shop_enabled(tenant):
        raise Http404
    shelves = shop_categories()
    category = None
    if slug:
        category = get_object_or_404(MenuCategory, slug=slug, active=True)
    query = request.GET.get("q", "")
    sort = request.GET.get("sort", "featured")
    if sort not in SHOP_SORTS:
        sort = "featured"
    items = list(search_shop(category=category, query=query, sort=sort))
    sub_shelves = []
    if category is not None:
        sub_shelves = [c for c in category.children.filter(active=True).exclude(slug="")
                       if search_shop(category=c).exists()]
    cart = Cart(request)
    return render(
        request,
        "storefront/shop.html",
        {
            "shelves": shelves,
            "category": category,
            "sub_shelves": sub_shelves,
            "items": items,
            "query": query.strip(),
            "sort": sort,
            "sorts": [("featured", "Featured"), ("price", "Price: low to high"),
                      ("-price", "Price: high to low"), ("name", "Name")],
            "cart": cart,
            "cart_quantities": cart.items if cart.is_courier else {},
            "ordering_enabled": tenant.feature("website_ordering"),
            "pages": _nav_pages(),
        },
    )


def item_detail(request, pk):
    """One shop product, with a few more from the same shelf."""
    tenant = request.tenant
    if not _shop_enabled(tenant):
        raise Http404
    item = get_object_or_404(MenuItem, pk=pk, active=True, fulfilment="courier")
    related = []
    if item.category_id:
        top, depth = item.category, 0
        while top.parent_id and depth < 6:  # a bad parent edit must not loop forever
            top, depth = top.parent, depth + 1
        related = list(
            shop_items().filter(category_id__in=category_family_ids(top))
            .exclude(pk=item.pk).exclude(image="").order_by("sort", "name")[:4]
        )
    cart = Cart(request)
    return render(
        request,
        "storefront/item.html",
        {
            "item": item,
            "related": related,
            "cart": cart,
            "qty": cart.items.get(str(item.pk), 0) if cart.is_courier else 0,
            "ordering_enabled": tenant.feature("website_ordering"),
            "pages": _nav_pages(),
            "shelves": shop_categories(),
        },
    )


log = logging.getLogger(__name__)


def csrf_failure(request, reason=""):
    """A form was submitted from a stale page (the browser's security token was
    renewed -- e.g. by logging in to the admin in another tab -- or the page sat
    open for a long time). Customers get a reload and a sentence, not a raw 403;
    the real reason goes to the log so it can be diagnosed."""
    log.warning("CSRF failure on %s %s from host %s: %s", request.method, request.path,
                request.get_host(), reason)
    if request.path.startswith("/cart/") and request.tenant is not None:
        messages.error(request, "That page was out of date. Please try again.")
        return redirect("storefront:cart")
    return HttpResponseForbidden(
        "<!doctype html><meta charset=utf-8><title>Please reload</title>"
        "<body style=\"font:16px system-ui;max-width:32rem;margin:4rem auto;padding:0 1rem\">"
        "<h1>That page was out of date</h1><p>Please go back, reload the page, and try again.</p>"
        "<p><a href=\"/\">Back to the home page</a></p></body>",
        content_type="text/html",
    )
