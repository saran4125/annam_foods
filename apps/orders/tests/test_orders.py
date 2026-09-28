"""Order creation. Both channels come through one function, so the rules here
are the rules everywhere."""
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.catalog.models import MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.delivery.models import DeliveryZone
from apps.orders import services
from apps.orders.models import Channel, Order, OrderEvent, OrderStatus
from apps.orders.services import RequestedLine
from apps.tenancy.context import all_tenants, tenant_context
from apps.tenancy.models import Tenant, TenantStatus

DAY = date(2026, 9, 7)
NOON = timezone.make_aware(datetime.combine(DAY, time(12, 0)))


@pytest.fixture
def kitchen(db):
    return Tenant.objects.create(slug="annam", name="Annam Foods", status=TenantStatus.ACTIVE)


@pytest.fixture
def shop(kitchen):
    """An open lunch slot, two dishes, one serviceable zone with a ₹150 minimum."""
    with tenant_context(kitchen):
        slot = Slot.objects.create(key="lunch", label="Lunch", order_cutoff=time(15, 0))
        meals = MenuItem.objects.create(name="Veg Meals", price=Decimal("120"))
        curd = MenuItem.objects.create(name="Curd Rice", price=Decimal("60"))
        for item in (meals, curd):
            MenuSchedule.objects.create(
                item=item, slot=slot, mode=ScheduleMode.DATE, on_date=DAY
            )
        DeliveryZone.objects.create(
            pincode="641001", area_name="RS Puram",
            delivery_fee=Decimal("20"), min_order=Decimal("150"),
        )
        customer = services.get_or_create_customer(kitchen, phone="919551079550", name="Hari")
        yield {"slot": slot, "meals": meals, "curd": curd, "customer": customer}


ADDRESS = {"line1": "12 Mettupalayam Rd", "pincode": "641001", "area": "RS Puram"}


def place(kitchen, shop, lines=None, **kw):
    # `is None`, not `or` -- an empty list is a real thing to pass, and
    # collapsing it to the default silently disarms the empty-order test.
    if lines is None:
        lines = [RequestedLine(shop["meals"].id, 2)]
    return services.create_order(
        kitchen,
        customer=shop["customer"],
        requested=lines,
        slot=shop["slot"], delivery_date=DAY,
        address_snapshot=dict(ADDRESS), now=NOON, **kw,
    )


# --- the happy path ---------------------------------------------------------

def test_an_order_totals_what_the_live_menu_says(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        assert order.subtotal == Decimal("240")     # 2 × 120
        assert order.delivery_fee == Decimal("20")
        assert order.total == Decimal("260")
        assert order.status == OrderStatus.PLACED
        assert order.item_count == 2


def test_the_order_number_carries_the_tenant_and_date(kitchen, shop):
    with tenant_context(kitchen):
        assert place(kitchen, shop).order_no.startswith("ANNAM-20260907-")


def test_placing_an_order_writes_its_first_event(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        event = OrderEvent.objects.get(order=order)
        assert event.to_status == OrderStatus.PLACED and event.from_status == ""


# --- prices are ours, not the caller's --------------------------------------

def test_prices_come_from_the_menu_not_the_request(kitchen, shop):
    """The caller supplies quantities only — there is nowhere to put a price."""
    with tenant_context(kitchen):
        order = place(kitchen, shop, [RequestedLine(shop["curd"].id, 3)])
        assert order.subtotal == Decimal("180")
        assert order.items[0]["unit_price"] == "60.00"


def test_the_order_snapshots_its_lines(kitchen, shop):
    """A price change next week must not rewrite last week's bill."""
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        shop["meals"].price = Decimal("500")
        shop["meals"].save()
        order.refresh_from_db()
        assert order.items[0]["unit_price"] == "120.00"
        assert order.total == Decimal("260")


def test_an_item_not_on_the_menu_is_refused(kitchen, shop):
    with tenant_context(kitchen):
        ghost = MenuItem.objects.create(name="Off-menu", price=Decimal("99"))
        with pytest.raises(services.ItemNotOnMenu):
            place(kitchen, shop, [RequestedLine(ghost.id, 1)])


# --- the gates --------------------------------------------------------------

def test_an_empty_order_is_refused(kitchen, shop):
    with tenant_context(kitchen), pytest.raises(services.EmptyOrder):
        place(kitchen, shop, [])


def test_a_closed_slot_is_refused(kitchen, shop):
    late = timezone.make_aware(datetime.combine(DAY, time(20, 0)))
    with tenant_context(kitchen), pytest.raises(services.SlotClosed):
        services.create_order(
            kitchen, customer=shop["customer"],
            requested=[RequestedLine(shop["meals"].id, 2)],
            slot=shop["slot"], delivery_date=DAY,
            address_snapshot=dict(ADDRESS), now=late,
        )


def test_an_unserviceable_pincode_is_refused(kitchen, shop):
    with tenant_context(kitchen), pytest.raises(services.NotServiceable):
        services.create_order(
            kitchen, customer=shop["customer"],
            requested=[RequestedLine(shop["meals"].id, 2)],
            slot=shop["slot"], delivery_date=DAY,
            address_snapshot={"line1": "x", "pincode": "110001"}, now=NOON,
        )


def test_below_the_zone_minimum_is_refused_with_the_shortfall(kitchen, shop):
    with tenant_context(kitchen):
        with pytest.raises(services.BelowMinimum) as exc:
            place(kitchen, shop, [RequestedLine(shop["curd"].id, 1)])   # ₹60 of ₹150
        assert exc.value.shortfall == Decimal("90")


def test_a_suspended_kitchen_cannot_take_an_order(kitchen, shop):
    kitchen.status = TenantStatus.SUSPENDED
    kitchen.save()
    with tenant_context(kitchen), pytest.raises(services.KitchenNotAccepting):
        place(kitchen, shop)


def test_a_restricted_kitchen_still_takes_orders(kitchen, shop):
    """Restricted squeezes the owner, never his customers."""
    kitchen.status = TenantStatus.RESTRICTED
    kitchen.save()
    with tenant_context(kitchen):
        assert place(kitchen, shop).total == Decimal("260")


# --- one order book ---------------------------------------------------------

def test_both_channels_produce_the_same_record(kitchen, shop):
    """The product's whole promise: only `channel` differs."""
    with tenant_context(kitchen):
        web = place(kitchen, shop, channel=Channel.WEB)
        wa = place(kitchen, shop, channel=Channel.WHATSAPP)
        assert web.channel == "web" and wa.channel == "whatsapp"
        for field in ("subtotal", "delivery_fee", "total", "items", "address"):
            assert getattr(web, field) == getattr(wa, field)
        assert Order.objects.count() == 2       # one list, both channels


# --- status flow ------------------------------------------------------------

def test_status_moves_forward_and_records_who_did_it(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        services.advance_status(order, OrderStatus.CONFIRMED, actor="owner:hari")
        order.refresh_from_db()
        assert order.status == OrderStatus.CONFIRMED
        assert order.events.last().actor == "owner:hari"


def test_status_cannot_skip_a_step(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        with pytest.raises(services.InvalidTransition):
            services.advance_status(order, OrderStatus.DELIVERED, actor="owner:hari")


def test_status_cannot_go_backwards(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        services.advance_status(order, OrderStatus.CONFIRMED, actor="owner:hari")
        with pytest.raises(services.InvalidTransition):
            services.advance_status(order, OrderStatus.PLACED, actor="owner:hari")


def test_an_order_can_be_cancelled_from_anywhere_live(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        services.advance_status(order, OrderStatus.CONFIRMED, actor="owner:hari")
        services.advance_status(order, OrderStatus.CANCELLED, actor="owner:hari",
                                note="kitchen ran out")
        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED
        assert order.cancelled_reason == "kitchen ran out"


def test_a_delivered_order_is_final(kitchen, shop):
    with tenant_context(kitchen):
        order = place(kitchen, shop)
        for nxt in (OrderStatus.CONFIRMED, OrderStatus.PREPARING,
                    OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED):
            services.advance_status(order, nxt, actor="owner:hari")
        with pytest.raises(services.InvalidTransition):
            services.advance_status(order, OrderStatus.CANCELLED, actor="owner:hari")


# --- customers and isolation ------------------------------------------------

def test_a_returning_phone_number_is_the_same_customer(kitchen, shop):
    with tenant_context(kitchen):
        again = services.get_or_create_customer(kitchen, phone="919551079550")
        assert again.pk == shop["customer"].pk


def test_orders_do_not_leak_between_kitchens(kitchen, shop, db):
    rival = Tenant.objects.create(slug="rival", name="Rival", status=TenantStatus.ACTIVE)
    with tenant_context(kitchen):
        place(kitchen, shop)
    with tenant_context(rival):
        assert Order.objects.count() == 0
    with all_tenants():
        assert Order.objects.count() == 1


def test_the_same_phone_is_a_separate_customer_per_kitchen(kitchen, shop, db):
    rival = Tenant.objects.create(slug="rival", name="Rival", status=TenantStatus.ACTIVE)
    with tenant_context(rival):
        other = services.get_or_create_customer(rival, phone="919551079550")
    assert other.pk != shop["customer"].pk
