from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.catalog.daily_menus import save_daily_menu, set_daily_availability
from apps.catalog.models import MenuDay, MenuItem, MenuSchedule, Slot
from apps.catalog.services import resolve_menu
from apps.orders.services import RequestedLine, price_lines
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantConfig, TenantDomain

DAY = date(2026, 11, 16)


@pytest.fixture
def repeating(db):
    tenant = Tenant.objects.create(slug='annam', name='Annam', status='active')
    TenantDomain.objects.create(tenant=tenant, hostname='annam.localhost', is_primary=True)
    TenantConfig.objects.filter(tenant=tenant).update(features={'carry_forward_breakfast': True})
    tenant.refresh_from_db()
    with tenant_context(tenant):
        slot = Slot.objects.create(key='breakfast', label='Breakfast', order_cutoff=time(23, 59))
        idly = MenuItem.objects.create(name='Fresh idly', price=100)
        dosa = MenuItem.objects.create(name='Fresh dosa', price=120)
    return tenant, slot, idly, dosa


def names(day, slot):
    return [entry.item.name for entry in resolve_menu(day, slot)]


def test_saved_breakfast_continues_in_tomorrows_public_menu_and_order_pricing(client, repeating):
    tenant, slot, idly, _ = repeating
    tomorrow = DAY + timedelta(days=1)
    with tenant_context(tenant):
        save_daily_menu(slot=slot, on_date=DAY, item_ids=[idly.pk], revision=0)
        assert names(tomorrow, slot) == [idly.name]
        assert names(DAY + timedelta(days=7), slot) == [idly.name]
        assert names(DAY - timedelta(days=1), slot) == []
        lines, subtotal = price_lines([RequestedLine(idly.pk, 2)], delivery_date=tomorrow, slot=slot)
        assert subtotal == 200 and lines[0]['item_id'] == idly.pk
        assert MenuDay.objects.count() == 1  # Read-only fallback doesn't create future plans.
    now = timezone.make_aware(datetime.combine(DAY, time(12)))
    with patch('django.utils.timezone.localdate', return_value=DAY), patch('django.utils.timezone.localtime', return_value=now):
        response = client.get(f'/menu/?date={tomorrow.isoformat()}&slot=breakfast', HTTP_HOST='annam.localhost')
    assert response.status_code == 200 and idly.name.encode() in response.content


def test_additions_removals_and_empty_menus_become_the_default_without_rewriting_saved_dates(repeating):
    tenant, slot, idly, dosa = repeating
    with tenant_context(tenant):
        save_daily_menu(slot=slot, on_date=DAY, item_ids=[idly.pk], revision=0)
        tomorrow = DAY + timedelta(days=1)
        set_daily_availability(slot=slot, on_date=tomorrow, item=idly, available=False, revision=0)
        set_daily_availability(slot=slot, on_date=tomorrow, item=dosa, available=True, revision=1)
        assert names(DAY, slot) == [idly.name]
        assert names(tomorrow, slot) == [dosa.name]
        assert names(DAY + timedelta(days=2), slot) == [dosa.name]
        saved = DAY + timedelta(days=5)
        save_daily_menu(slot=slot, on_date=saved, item_ids=[idly.pk], revision=0)
        save_daily_menu(slot=slot, on_date=DAY + timedelta(days=3), item_ids=[], revision=0)
        assert names(DAY + timedelta(days=3), slot) == []
        assert names(DAY + timedelta(days=4), slot) == []
        assert names(saved, slot) == [idly.name]
        assert names(saved + timedelta(days=1), slot) == [idly.name]


def test_daily_sales_reset_when_inherited_but_global_stock_and_source_date_are_preserved(repeating):
    tenant, slot, idly, _ = repeating
    with tenant_context(tenant):
        save_daily_menu(slot=slot, on_date=DAY, item_ids=[idly.pk], revision=0)
        source = MenuSchedule.objects.get(item=idly, slot=slot, on_date=DAY)
        source.qty_limit = source.qty_sold = 1
        source.price_override = Decimal('99.50')
        source.save()
        assert names(DAY, slot) == []
        tomorrow = DAY + timedelta(days=1)
        assert resolve_menu(tomorrow, slot)[0].price == Decimal('99.50')
        set_daily_availability(slot=slot, on_date=tomorrow, item=idly, available=True, revision=0)
        target = MenuSchedule.objects.get(item=idly, slot=slot, on_date=tomorrow)
        source.refresh_from_db()
        assert source.qty_sold == 1 and target.qty_sold == 0 and target.qty_limit == 1
        idly.in_stock = False
        idly.save()
        assert names(tomorrow, slot) == []


def test_other_meals_and_other_stores_do_not_inherit_breakfast(repeating):
    tenant, slot, idly, _ = repeating
    other = Tenant.objects.create(slug='other', name='Other', status='active')
    with tenant_context(tenant):
        lunch = Slot.objects.create(key='lunch', label='Lunch', order_cutoff=time(23, 59))
        save_daily_menu(slot=slot, on_date=DAY, item_ids=[idly.pk], revision=0)
        save_daily_menu(slot=lunch, on_date=DAY, item_ids=[idly.pk], revision=0)
        assert names(DAY + timedelta(days=1), lunch) == []
    with tenant_context(other):
        own_slot = Slot.objects.create(key='breakfast', label='Breakfast', order_cutoff=time(23, 59))
        assert names(DAY + timedelta(days=1), own_slot) == []


@pytest.mark.parametrize('meal', ['breakfast', 'lunch', 'dinner'])
def test_all_requested_meals_repeat_their_own_menu_until_changed(repeating, meal):
    tenant, _, idly, dosa = repeating
    config = TenantConfig.objects.get(tenant=tenant)
    config.features = {'carry_forward_meals': True}
    config.save(update_fields=['features'])
    tenant.refresh_from_db()
    with tenant_context(tenant):
        slot, _ = Slot.objects.get_or_create(key=meal, defaults={'label': meal.title(), 'order_cutoff': time(23, 59)})
        save_daily_menu(slot=slot, on_date=DAY, item_ids=[idly.pk], revision=0)
        assert names(DAY + timedelta(days=1), slot) == [idly.name]
        save_daily_menu(slot=slot, on_date=DAY + timedelta(days=1), item_ids=[dosa.pk], revision=0)
        assert names(DAY, slot) == [idly.name]
        assert names(DAY + timedelta(days=2), slot) == [dosa.name]
        snacks = Slot.objects.create(key='snacks', label='Snacks', order_cutoff=time(23, 59))
        assert names(DAY + timedelta(days=2), snacks) == []


def test_switching_meal_repetition_off_overrides_the_legacy_breakfast_setting(repeating):
    tenant, slot, idly, _ = repeating
    config = TenantConfig.objects.get(tenant=tenant)
    config.features = {'carry_forward_breakfast': True, 'carry_forward_meals': False}
    config.save(update_fields=['features'])
    tenant.refresh_from_db()
    with tenant_context(tenant):
        save_daily_menu(slot=slot, on_date=DAY, item_ids=[idly.pk], revision=0)
        assert names(DAY + timedelta(days=1), slot) == []
