"""The schedule table's shape is enforced by the database, not by hope."""
from datetime import date, time
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import MenuItem, MenuSchedule, ScheduleMode, Slot
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

MONDAY = date(2026, 9, 7)


@pytest.fixture
def kitchen(db):
    return Tenant.objects.create(slug="annam", name="Annam Foods", status="active")


@pytest.fixture
def setup(kitchen):
    with tenant_context(kitchen):
        slot = Slot.objects.create(key="lunch", label="Lunch", order_cutoff=time(11, 0))
        item = MenuItem.objects.create(name="Idly", price=Decimal("40"))
        yield kitchen, slot, item


def test_dated_row_without_a_date_is_rejected(setup):
    kitchen, slot, item = setup
    with tenant_context(kitchen), pytest.raises(IntegrityError):
        with transaction.atomic():
            MenuSchedule.objects.create(item=item, slot=slot, mode=ScheduleMode.DATE)


def test_weekly_row_without_a_weekday_is_rejected(setup):
    kitchen, slot, item = setup
    with tenant_context(kitchen), pytest.raises(IntegrityError):
        with transaction.atomic():
            MenuSchedule.objects.create(item=item, slot=slot, mode=ScheduleMode.WEEKDAY)


def test_a_row_cannot_be_both_dated_and_weekly(setup):
    kitchen, slot, item = setup
    with tenant_context(kitchen), pytest.raises(IntegrityError):
        with transaction.atomic():
            MenuSchedule.objects.create(
                item=item, slot=slot, mode=ScheduleMode.DATE,
                on_date=MONDAY, weekday=0,
            )


def test_the_same_item_cannot_be_scheduled_twice_for_one_date(setup):
    kitchen, slot, item = setup
    with tenant_context(kitchen):
        MenuSchedule.objects.create(
            item=item, slot=slot, mode=ScheduleMode.DATE, on_date=MONDAY
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            MenuSchedule.objects.create(
                item=item, slot=slot, mode=ScheduleMode.DATE, on_date=MONDAY
            )


def test_the_same_item_cannot_be_scheduled_twice_for_one_weekday(setup):
    kitchen, slot, item = setup
    with tenant_context(kitchen):
        MenuSchedule.objects.create(
            item=item, slot=slot, mode=ScheduleMode.WEEKDAY, weekday=0
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            MenuSchedule.objects.create(
                item=item, slot=slot, mode=ScheduleMode.WEEKDAY, weekday=0
            )


def test_dated_and_weekly_rows_coexist_for_the_same_item(setup):
    """This pair is the override case, so it must be allowed."""
    kitchen, slot, item = setup
    with tenant_context(kitchen):
        MenuSchedule.objects.create(
            item=item, slot=slot, mode=ScheduleMode.WEEKDAY, weekday=0
        )
        MenuSchedule.objects.create(
            item=item, slot=slot, mode=ScheduleMode.DATE, on_date=MONDAY, available=False
        )
        assert MenuSchedule.objects.count() == 2


def test_two_kitchens_can_use_the_same_slot_key(kitchen, db):
    rival = Tenant.objects.create(slug="rival", name="Rival", status="active")
    with tenant_context(kitchen):
        Slot.objects.create(key="lunch", label="Lunch", order_cutoff=time(11, 0))
    with tenant_context(rival):
        Slot.objects.create(key="lunch", label="Lunch", order_cutoff=time(12, 0))
    from apps.tenancy.context import all_tenants
    with all_tenants():
        assert Slot.objects.filter(key="lunch").count() == 2
