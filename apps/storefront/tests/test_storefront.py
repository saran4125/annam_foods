"""The storefront as a customer meets it."""
from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.content.models import Page
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
    """A lunch slot that is still open, with one dish on today's menu."""
    today = timezone.localdate()
    late = (timezone.localtime() + timedelta(hours=3)).time()
    with tenant_context(kitchen):
        slot = Slot.objects.create(key="lunch", label="Lunch", order_cutoff=late, sort=1)
        item = MenuItem.objects.create(name="Veg Meals", price=Decimal("120"))
        MenuSchedule.objects.create(
            item=item, slot=slot, mode=ScheduleMode.DATE, on_date=today
        )
        DeliveryZone.objects.create(
            pincode="641001", area_name="RS Puram",
            delivery_fee=Decimal("20"), min_order=Decimal("150"),
        )
    return {"slot": slot, "item": item, "date": today}


def test_home_renders_with_the_kitchens_brand(client, kitchen, menu):
    r = client.get("/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Annam Foods" in r.content


def test_menu_lists_todays_dishes(client, kitchen, menu):
    r = client.get("/menu/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Veg Meals" in r.content
    assert b"120" in r.content


def test_adding_to_cart_updates_the_count(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)  # sets slot/date context
    r = client.post(
        "/cart/add/", {"item_id": menu["item"].id, "delta": 1},
        HTTP_HOST=HOST, follow=True,
    )
    assert r.status_code == 200
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Veg Meals" in r.content


def test_cart_prices_from_the_live_menu_not_the_session(client, kitchen, menu):
    """A stale price in someone's browser must not decide what they pay."""
    client.get("/menu/", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
    with tenant_context(kitchen):
        menu["item"].price = Decimal("140")
        menu["item"].save()
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"140" in r.content


def test_unserviceable_pincode_is_refused(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
    r = client.post("/cart/pincode/", {"pincode": "110001"}, HTTP_HOST=HOST, follow=True)
    assert b"don" in r.content and b"110001" in r.content


def test_spaced_pincode_is_accepted(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
    r = client.post("/cart/pincode/", {"pincode": "641 001"}, HTTP_HOST=HOST, follow=True)
    assert b"RS Puram" in r.content


def test_below_minimum_order_blocks_checkout(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)  # 120 < 150
    client.post("/cart/pincode/", {"pincode": "641001"}, HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Minimum order not met" in r.content
    assert b"30" in r.content  # shortfall


def test_meeting_the_minimum_clears_the_block(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id, "delta": 2}, HTTP_HOST=HOST)
    client.post("/cart/pincode/", {"pincode": "641001"}, HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Minimum order not met" not in r.content
    assert b"260" in r.content  # 240 + 20 delivery


def test_switching_slot_empties_the_cart(client, kitchen, menu):
    """A lunch dish can't be carried into a dinner order."""
    with tenant_context(kitchen):
        Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(23, 0), sort=2)
    client.get("/menu/?slot=lunch", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
    client.get("/menu/?slot=dinner", HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Your cart is empty" in r.content


# --- the suspension ladder, as customers see it -----------------------------

def test_suspended_kitchen_still_shows_its_menu(client, kitchen, menu):
    """Suspension stops ordering. It does not take the site down."""
    kitchen.status = TenantStatus.SUSPENDED
    kitchen.save()
    r = client.get("/menu/", HTTP_HOST=HOST)
    assert r.status_code == 200
    assert b"Veg Meals" in r.content
    assert b"isn" in r.content  # "isn't accepting online orders"


def test_suspended_kitchen_refuses_to_add_to_cart(client, kitchen, menu):
    client.get("/menu/", HTTP_HOST=HOST)
    kitchen.status = TenantStatus.SUSPENDED
    kitchen.save()
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
    r = client.get("/cart/", HTTP_HOST=HOST)
    assert b"Your cart is empty" in r.content


def test_restricted_kitchen_keeps_selling(client, kitchen, menu):
    """Restricted squeezes the owner, not his customers."""
    kitchen.status = TenantStatus.RESTRICTED
    kitchen.save()
    client.get("/menu/", HTTP_HOST=HOST)
    client.post("/cart/add/", {"item_id": menu["item"].id}, HTTP_HOST=HOST)
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
    today = timezone.localdate()
    now = timezone.localtime()
    past = (now - timedelta(hours=2)).time()
    future = (now + timedelta(hours=3)).time()

    with tenant_context(kitchen):
        shut = Slot.objects.create(key="breakfast", label="Breakfast", order_cutoff=past, sort=1)
        open_slot = Slot.objects.create(key="dinner", label="Dinner", order_cutoff=future, sort=2)
        early = MenuItem.objects.create(name="Idly", price=Decimal("40"))
        late = MenuItem.objects.create(name="Parotta", price=Decimal("80"))
        MenuSchedule.objects.create(item=early, slot=shut, mode=ScheduleMode.DATE, on_date=today)
        MenuSchedule.objects.create(item=late, slot=open_slot, mode=ScheduleMode.DATE, on_date=today)

    r = client.get("/menu/", HTTP_HOST=HOST)
    assert b"Parotta" in r.content
    assert b"Idly" not in r.content


def test_an_explicitly_chosen_closed_slot_is_still_shown(client, kitchen, db):
    """Choosing a closed slot shows it, read-only — the customer asked for it."""
    today = timezone.localdate()
    past = (timezone.localtime() - timedelta(hours=2)).time()
    future = (timezone.localtime() + timedelta(hours=3)).time()
    with tenant_context(kitchen):
        shut = Slot.objects.create(key="breakfast", label="Breakfast", order_cutoff=past, sort=1)
        Slot.objects.create(key="dinner", label="Dinner", order_cutoff=future, sort=2)
        item = MenuItem.objects.create(name="Idly", price=Decimal("40"))
        MenuSchedule.objects.create(item=item, slot=shut, mode=ScheduleMode.DATE, on_date=today)

    r = client.get("/menu/?slot=breakfast", HTTP_HOST=HOST)
    assert b"Idly" in r.content
    assert b"btn-add" not in r.content        # visible, not orderable
    assert b"closed at" in r.content
