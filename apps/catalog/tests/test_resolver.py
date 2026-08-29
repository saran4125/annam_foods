"""The menu resolver is where daily and weekly planning both come from one
table. If these break, kitchens serve the wrong food."""
from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.catalog.services import open_slots, resolve_menu, slot_is_open
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

# 2026-09-07 is a Monday, so weekday() == 0
MONDAY = date(2026, 9, 7)
TUESDAY = date(2026, 9, 8)


@pytest.fixture
def kitchen(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    with tenant_context(t):
        yield t


@pytest.fixture
def lunch(kitchen):
    with tenant_context(kitchen):
        return Slot.objects.create(
            key="lunch", label="Lunch", order_cutoff=time(11, 0), sort=1
        )


@pytest.fixture
def idly(kitchen):
    with tenant_context(kitchen):
        cat = MenuCategory.objects.create(name="Tiffin")
        return MenuItem.objects.create(name="Idly", price=Decimal("40.00"), category=cat)


@pytest.fixture
def dosa(kitchen):
    with tenant_context(kitchen):
        return MenuItem.objects.create(name="Dosa", price=Decimal("60.00"))


def weekly(item, slot, weekday, **kw):
    return MenuSchedule.objects.create(
        item=item, slot=slot, mode=ScheduleMode.WEEKDAY, weekday=weekday, **kw
    )


def dated(item, slot, on_date, **kw):
    return MenuSchedule.objects.create(
        item=item, slot=slot, mode=ScheduleMode.DATE, on_date=on_date, **kw
    )


# --- the two planning styles ------------------------------------------------

def test_weekly_template_puts_an_item_on_the_menu(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0)
        assert [e.item for e in resolve_menu(MONDAY, lunch)] == [idly]
        assert resolve_menu(TUESDAY, lunch) == []


def test_dated_row_puts_an_item_on_one_day_only(kitchen, lunch, idly):
    with tenant_context(kitchen):
        dated(idly, lunch, MONDAY)
        assert [e.item for e in resolve_menu(MONDAY, lunch)] == [idly]
        assert resolve_menu(TUESDAY, lunch) == []


# --- the override, which is the point of the design -------------------------

def test_dated_row_overrides_the_weekly_template(kitchen, lunch, idly):
    """A weekly kitchen pulls one dish on one day without touching its template."""
    with tenant_context(kitchen):
        weekly(idly, lunch, 0, available=True)
        dated(idly, lunch, MONDAY, available=False)

        assert resolve_menu(MONDAY, lunch) == []          # pulled that day
        next_monday = date(2026, 9, 14)
        assert [e.item for e in resolve_menu(next_monday, lunch)] == [idly]  # template intact


def test_dated_row_can_override_price_for_one_day(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0)
        dated(idly, lunch, MONDAY, price_override=Decimal("35.00"))
        entry = resolve_menu(MONDAY, lunch)[0]
        assert entry.price == Decimal("35.00")
        assert entry.source == "date"


def test_template_price_applies_when_no_override(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0)
        entry = resolve_menu(MONDAY, lunch)[0]
        assert entry.price == Decimal("40.00")
        assert entry.source == "weekday"


# --- availability -----------------------------------------------------------

def test_sold_out_items_drop_off_the_menu(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0, qty_limit=10, qty_sold=10)
        assert resolve_menu(MONDAY, lunch) == []


def test_partially_sold_items_stay_on_the_menu(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0, qty_limit=10, qty_sold=9)
        assert len(resolve_menu(MONDAY, lunch)) == 1


def test_deactivating_an_item_removes_it_everywhere(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0)
        idly.active = False
        idly.save()
        assert resolve_menu(MONDAY, lunch) == []


def test_owner_can_see_unavailable_items_when_editing(kitchen, lunch, idly):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0, available=False)
        assert resolve_menu(MONDAY, lunch) == []
        assert len(resolve_menu(MONDAY, lunch, include_unavailable=True)) == 1


def test_menu_mixes_both_row_kinds(kitchen, lunch, idly, dosa):
    with tenant_context(kitchen):
        weekly(idly, lunch, 0)
        dated(dosa, lunch, MONDAY)
        assert {e.item for e in resolve_menu(MONDAY, lunch)} == {idly, dosa}


# --- cutoffs ----------------------------------------------------------------

def test_slot_closes_at_its_cutoff(kitchen, lunch):
    with tenant_context(kitchen):
        before = timezone.make_aware(datetime.combine(MONDAY, time(10, 30)))
        after = timezone.make_aware(datetime.combine(MONDAY, time(14, 0)))
        assert slot_is_open(lunch, MONDAY, now=before) is True
        assert slot_is_open(lunch, MONDAY, now=after) is False


def test_open_slots_excludes_the_closed_ones(kitchen, lunch):
    with tenant_context(kitchen):
        Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(19, 0), sort=2)
        at_noon = timezone.make_aware(datetime.combine(MONDAY, time(12, 0)))
        keys = [s.key for s in open_slots(MONDAY, now=at_noon)]
        assert keys == ["dinner"]  # lunch cutoff was 11:00


# --- isolation still holds --------------------------------------------------

def test_menu_does_not_leak_between_kitchens(kitchen, lunch, idly, db):
    rival = Tenant.objects.create(slug="rival", name="Rival", status="active")
    with tenant_context(kitchen):
        weekly(idly, lunch, 0)
    with tenant_context(rival):
        assert resolve_menu(MONDAY, lunch) == []
