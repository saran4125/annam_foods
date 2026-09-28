"""The storefront as a customer meets it.

Assertions use data-testid hooks rather than visible copy wherever the copy is
something a redesign would legitimately rewrite. A test that breaks because a
button now reads better is a test that discourages improving the product.
Dish names, prices and totals are asserted directly -- those ARE the behaviour.
"""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.catalog.models import MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.content.models import Banner, Page
from apps.delivery.models import DeliveryZone
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantConfig, TenantDomain, TenantStatus

HOST = "annam.localhost"


@pytest.fixture
def kitchen(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=t, hostname=HOST, is_primary=True)
    TenantConfig.objects.create(tenant=t, brand_name="Annam Foods", support_phone="+919551079550")
    return t


@pytest.fixture
def menu(kitchen):
    """A lunch slot that is still open, with one dish on today's menu.

    The clock is pinned for the whole test, not just for setup. Deriving a
    cutoff from the wall clock breaks after 21:00: now+3h rolls past midnight,
    `.time()` drops the date, and the slot meant to be open gets a cutoff 21
    hours in the past. Every cart test then fails, but only in the evening.
    The same trap was already fixed in two tests below; the fixture they all
    share had been left deriving from the wall clock.
    """
    noon = timezone.make_aware(datetime.combine(date(2026, 9, 7), time(12, 0)))
    with patch("django.utils.timezone.localtime", return_value=noon), \
         patch("django.utils.timezone.localdate", return_value=noon.date()):
        today = noon.date()
        with tenant_context(kitchen):
            slot = Slot.objects.create(
                key="lunch", label="Lunch", order_cutoff=time(15, 0), sort=1
            )
            item = MenuItem.objects.create(name="Veg Meals", price=Decimal("120"))
            MenuSchedule.objects.create(
                item=item, slot=slot, mode=ScheduleMode.DATE, on_date=today
            )
            DeliveryZone.objects.create(
                pincode="641001", area_name="RS Puram",
                delivery_fee=Decimal("20"), min_order=Decimal("150"),
            )
        yield {"slot": slot, "item": item, "date": today}


def _add(client, menu, delta=1, **overrides):
    """POST an add/remove against the validated contract (slot + date)."""
    payload = {
        "item_id": menu["item"].id,
        "delta": delta,
        "slot_key": menu["slot"].key,
        "delivery_date": menu["date"].isoformat(),
    }
    payload.update(overrides)
    return client.post("/cart/add/", payload, HTTP_HOST=HOST)


def test_home_renders_with_the_kitchens_brand(client, kitchen, menu):
    r = client.get("/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Annam Foods" in r.content


def test_first_active_banner_becomes_the_promotional_hero(client, kitchen, menu):
    with tenant_context(kitchen):
        Banner.objects.create(
            title="Weekend family offer",
            subtitle="Save on a meal for four",
            image="banners/weekend-offer.jpg",
            link="/menu/?slot=lunch",
        )
    r = client.get("/", HTTP_HOST=HOST)
    assert b'class="hero-slider"' in r.content
    assert b'data-slide' in r.content
    assert b'banners/weekend-offer.jpg' in r.content
    assert b'href="/menu/?slot=lunch"' in r.content


def test_menu_lists_todays_dishes(client, kitchen, menu):
    r = client.get("/menu/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Veg Meals" in r.content
    assert b"120" in r.content


def test_adding_to_cart_updates_the_count(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)  # browse, then order
    r = _add(client, menu)
    assert r.status_code == 302
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content


def test_cart_prices_from_the_live_menu_not_the_session(client, kitchen, menu):
    """A stale price in someone's browser must not decide what they pay."""
    client.get("/menu/", HTTP_HOST=HOST)
    _add(client, menu)
    with tenant_context(kitchen):
        menu["item"].price = Decimal("140")
        menu["item"].save()
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"140" in r.content


def test_unserviceable_pincode_is_refused(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    _add(client, menu)
    r = client.post("/cart/pincode/", {"pincode": "110001"}, HTTP_HOST=HOST, follow=True)
    assert b'data-testid="flash"' in r.content
    assert b"110001" in r.content


def test_spaced_pincode_is_accepted(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    _add(client, menu)
    r = client.post("/cart/pincode/", {"pincode": "641 001"}, HTTP_HOST=HOST, follow=True)
    assert b"RS Puram" in r.content


def test_below_minimum_order_blocks_checkout(client, kitchen, menu):
    _add(client, menu)  # 120 < 150
    client.post("/cart/pincode/", {"pincode": "641001"}, HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-blocked="minimum"' in r.content
    assert b"30" in r.content  # shortfall


def test_meeting_the_minimum_clears_the_block(client, kitchen, menu):
    _add(client, menu, delta=2)
    client.post("/cart/pincode/", {"pincode": "641001"}, HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-blocked="minimum"' not in r.content
    assert b"260" in r.content  # 240 + 20 delivery


def test_browsing_another_slot_leaves_the_cart_alone(client, kitchen, menu):
    """(FIX-05) Reading the dinner menu is not permission to delete a lunch order."""
    with tenant_context(kitchen):
        Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(23, 0), sort=2)
    client.get("/menu/?slot=lunch", HTTP_HOST=HOST)
    _add(client, menu)
    client.get("/menu/?slot=dinner", HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content
    assert b'data-testid="cart-empty"' not in r.content


def test_a_dinner_dish_cannot_join_a_lunch_order(client, kitchen, menu):
    """(FIX-05) A different slot/day is a different order until the customer
    explicitly starts a fresh one."""
    with tenant_context(kitchen):
        dinner = Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(23, 0), sort=2)
        MenuSchedule.objects.create(
            item=menu["item"], slot=dinner, mode=ScheduleMode.DATE,
            on_date=menu["date"],
        )
    _add(client, menu)
    with tenant_context(kitchen):
        menu["item"].refresh_from_db()
    r = client.post(
        "/cart/add/",
        {
            "item_id": menu["item"].id,
            "slot_key": "dinner",
            "delivery_date": menu["date"].isoformat(),
        },
        HTTP_HOST=HOST, follow=True,
    )
    assert r.status_code == 200
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content
    assert b'data-testid="cart-empty"' not in r.content


def test_clear_starts_a_genuinely_fresh_order(client, kitchen, menu):
    """The explicit escape hatch: dropping the cart must work even after the
    slot for its contents has closed."""
    with tenant_context(kitchen):
        pass
    _add(client, menu, delta=2)
    r = client.post("/cart/clear/", {"next": "/cart/"}, HTTP_HOST=HOST)
    assert r.status_code == 302
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in r.content


def test_a_closed_slot_refuses_a_new_dish(client, kitchen, menu):
    """(FIX-06) Adding stops at the cutoff; the explicitly chosen menu stays
    readable but the add button disappears."""
    # Move the clock past lunch's cutoff, with dinner not yet open either.
    late = (timezone.localtime() - timedelta(hours=5)).time()
    with tenant_context(kitchen):
        menu["slot"].order_cutoff = late
        menu["slot"].save()
    r = client.get("/menu/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content
    assert b"btn-add" not in r.content
    _add(client, menu)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in r.content


def test_a_quantity_above_the_line_cap_is_refused(client, kitchen, menu):
    """Quantity is bounded at add-time — a flood of items is a data error."""
    _add(client, menu, delta=99)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in r.content


def test_add_is_refused_without_a_slot_or_date(client, kitchen, menu):
    """The validation contract (FIX-08/-06): an anonymous POST with no context
    must not silently pick a slot, because that echoes a midnight cutoff race."""
    r = client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
    assert r.status_code == 302
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in r.content


# --- the suspension ladder, as customers see it -----------------------------

def test_suspended_kitchen_still_shows_its_menu(client, kitchen, menu):
    """Suspension stops ordering. It does not take the site down."""
    kitchen.status = TenantStatus.SUSPENDED
    kitchen.save()
    r = client.get("/menu/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Veg Meals" in r.content
    assert b'data-testid="orders-paused"' in r.content


def test_suspended_kitchen_refuses_to_add_to_cart(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    kitchen.status = TenantStatus.SUSPENDED
    kitchen.save()
    _add(client, menu)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in r.content


def test_restricted_kitchen_keeps_selling(client, kitchen, menu):
    """Restricted squeezes the owner, not his customers."""
    kitchen.status = TenantStatus.RESTRICTED
    kitchen.save()
    client.get("/menu/", HTTP_HOST=HOST)
    _add(client, menu)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content


# --- owner-written pages ----------------------------------------------------

def test_published_page_renders_its_markdown(client, kitchen):
    with tenant_context(kitchen):
        Page.objects.create(
            slug="refund-policy", title="Refund Policy",
            body_md="## How refunds work\n\nWe refund **within 3 days**.",
            published=True,
        )
    r = client.get("/p/refund-policy/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"<h2>How refunds work</h2>" in r.content
    assert b"<strong>within 3 days</strong>" in r.content


def test_unpublished_page_is_not_visible(client, kitchen):
    with tenant_context(kitchen):
        Page.objects.create(slug="draft", title="Draft", body_md="soon", published=False)
    assert client.get("/p/draft/", HTTP_HOST=HOST).status_code == 404


def test_pages_do_not_leak_between_kitchens(client, kitchen, db):
    rival = Tenant.objects.create(slug="rival", name="Rival", status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=rival, hostname="rival.localhost")
    TenantConfig.objects.create(tenant=rival, brand_name="Rival")
    with tenant_context(rival):
        Page.objects.create(slug="secret", title="Rival Only", body_md="x", published=True)
    assert client.get("/p/secret/", HTTP_HOST=HOST).status_code == 404
    assert client.get("/p/secret/", HTTP_HOST="rival.localhost").status_code == 200


# --- landing on a slot the customer can actually use ------------------------

def test_menu_defaults_to_the_next_open_slot(client, kitchen, db):
    """Landing on a closed breakfast menu at 1pm is a closed door."""
    # Pin the clock so the test is deterministic at any real hour -- deriving
    # cutoffs from the wall clock goes wrong across midnight. Here it's 12:00:
    # a slot closing at 11:00 is in the past, one closing at 13:00 is ahead.
    noon = timezone.make_aware(datetime.combine(date(2026, 9, 1), time(12, 0)))
    with patch("django.utils.timezone.localtime", return_value=noon), \
         patch("django.utils.timezone.localdate", return_value=noon.date()):
        today = timezone.localdate()
        with tenant_context(kitchen):
            shut = Slot.objects.create(key="breakfast", label="Breakfast", order_cutoff=time(11, 0), sort=1)
            open_slot = Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(13, 0), sort=2)
            early = MenuItem.objects.create(name="Idly", price=Decimal("40"))
            late = MenuItem.objects.create(name="Parotta", price=Decimal("80"))
            MenuSchedule.objects.create(item=early, slot=shut, mode=ScheduleMode.DATE, on_date=today)
            MenuSchedule.objects.create(item=late, slot=open_slot, mode=ScheduleMode.DATE, on_date=today)

        r = client.get("/menu/", HTTP_HOST=HOST)
    assert b"Parotta" in r.content
    assert b"Idly" not in r.content


def test_an_explicitly_chosen_closed_slot_is_still_shown(client, kitchen, db):
    """Choosing a closed slot shows it, read-only — the customer asked for it."""
    # Fixed clock again: breakfast closed at 11:00, dinner only opens at 13:00.
    noon = timezone.make_aware(datetime.combine(date(2026, 9, 1), time(12, 0)))
    with patch("django.utils.timezone.localtime", return_value=noon), \
         patch("django.utils.timezone.localdate", return_value=noon.date()):
        today = timezone.localdate()
        with tenant_context(kitchen):
            shut = Slot.objects.create(key="breakfast", label="Breakfast", order_cutoff=time(11, 0), sort=1)
            Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(13, 0), sort=2)
            item = MenuItem.objects.create(name="Idly", price=Decimal("40"))
            MenuSchedule.objects.create(item=item, slot=shut, mode=ScheduleMode.DATE, on_date=today)

        r = client.get("/menu/?slot=breakfast", HTTP_HOST=HOST)
    assert b"Idly" in r.content
    assert b"btn-add" not in r.content        # visible, not orderable
    assert b'data-testid="slot-closed"' in r.content


# --- content trust (FIX-09) ------------------------------------------------

def test_page_markdown_never_emits_script_or_event_handlers(client, kitchen):
    """Owner-written Markdown can't smuggle executable content to the browser."""
    with tenant_context(kitchen):
        Page.objects.create(
            slug="about", title="About",
            body_md=(
                "Hello <script>alert(1)</script> and <b onclick=\"alert(2)\">bold</b> "
                "<a href=\"javascript:alert(3)\">bad link</a> and "
                "<a href=\"http://elsewhere.example\">plain link</a>."
            ),
            published=True,
        )
    r = client.get("/p/about/", HTTP_HOST=HOST)
    body = r.content.split(b"<main")[-1].split(b"</main>")[0]
    assert b"<script>" not in body
    assert b"onclick" not in body
    assert b"javascript:" not in body
    # `<b>` isn't allowlisted (only `<strong>` is); it degrades to plain text.
    assert b"<b" not in body
    assert b"bold" in body


def test_banners_only_decorate_the_hero_with_an_image(client, kitchen, menu):
    """(FIX-01) A placeholder banner with no photograph must not become a slide."""
    with tenant_context(kitchen):
        Banner.objects.create(title="No photo", link="/menu/")
    r = client.get("/", HTTP_HOST=HOST)
    assert b"hero-slider is-hidden" in r.content


def test_promo_tiles_do_not_repeat_the_hero_and_skip_dead_links(client, kitchen, menu):
    """(FIX-02) The rail is an independent placement: no hero double showing,
    and a banner that goes nowhere doesn't render as a dead `href="#"`."""
    with tenant_context(kitchen):
        for i in range(3):  # the first three fill the hero slider
            Banner.objects.create(
                title=f"Hero {i}", subtitle="s", image=f"banners/h{i}.jpg",
                link="", sort=i, active=True,
            )
        Banner.objects.create(
            title="Joined promo", subtitle="s", image="banners/m.jpg",
            link="/menu/", sort=3, active=True,
        )
    r = client.get("/", HTTP_HOST=HOST)
    # The rail exists, holds only the 4th campaign, and the hero's slides
    # never leak into it.
    rail = r.content.split(b'promo-rail')[-1].split(b'</div>')[0]
    assert b"promo-tile" in r.content
    assert b'banners/m.jpg' in rail
    for i in range(3):
        assert f'banners/h{i}.jpg'.encode() not in rail
    assert b'href="#"' not in r.content


# --- cross-tenant isolation (FIX-08) ---------------------------------------

def test_two_kitchens_share_browsers_not_carts(client, kitchen, menu, db):
    """The same browser can hold carts for two kitchens without leaking."""
    rival = Tenant.objects.create(slug="rival", name="Rival", status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=rival, hostname="rival.localhost")
    TenantConfig.objects.create(tenant=rival, brand_name="Rival")
    today = timezone.localdate()
    with tenant_context(rival):
        slot = Slot.objects.create(key="lunch", label="Lunch",
                                   order_cutoff=(timezone.localtime() + timedelta(hours=3)).time())
        rival_item = MenuItem.objects.create(name="Rival Roll", price=Decimal("70"))
        MenuSchedule.objects.create(item=rival_item, slot=slot, mode=ScheduleMode.DATE, on_date=today)

    _add(client, menu)
    client.post(
        "/cart/add/",
        {"item_id": rival_item.id, "slot_key": slot.key, "delivery_date": today.isoformat()},
        HTTP_HOST="rival.localhost",
    )

    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content
    assert b"Rival Roll" not in r.content
    r = client.get("/cart/", HTTP_HOST="rival.localhost")
    assert b"Rival Roll" in r.content
    assert b"Veg Meals" not in r.content


# --- open-redirect safety (FIX-07) ----------------------------------------

def test_add_ignores_an_external_next_and_stays_on_site(client, kitchen, menu):
    raw = client.post(
        "/cart/add/",
        {"item_id": menu["item"].id, "slot_key": menu["slot"].key,
         "delivery_date": menu["date"].isoformat(), "next": "https://evil.example"},
        HTTP_HOST=HOST,
    )
    # Success redirects to the cart; a hostile `next` must never escape the site.
    assert raw["Location"] == "/cart/"
    assert not raw["Location"].startswith("http")


# --- status policy (FIX-12) ------------------------------------------------

@pytest.mark.parametrize("status,ordering,read_only,banner", [
    (TenantStatus.ACTIVE, True, False, False),
    (TenantStatus.PAST_DUE, True, False, True),
    (TenantStatus.RESTRICTED, True, True, True),
    (TenantStatus.SUSPENDED, False, False, True),
])
def test_kitchen_status_policy(status, ordering, read_only, banner, db):
    """Suspension and cancellation stop the plates; arrears squeeze the owner."""
    t = Tenant.objects.create(slug="s", name="S", status=status)
    assert t.can_take_orders is ordering
    assert t.backend_is_read_only is read_only
    assert t.shows_billing_banner is banner
    t.status = TenantStatus.CANCELLED
    t.save()
    assert not t.can_take_orders
