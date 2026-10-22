"""Date menus rotate independently; imported labels never decide recurrence."""
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.catalog.models import MenuDay, MenuItem, MenuSchedule
from apps.catalog.services import resolve_menu
from apps.catalog.daily_menus import save_daily_menu, set_daily_availability
from apps.orders.services import price_lines, RequestedLine, ItemNotOnMenu
from apps.tenancy.context import tenant_context
from .test_menu_groups import grouped
from .test_owner import kitchens, catalog, signed_in, owner, HOST, OTHER

DAY = date(2026, 10, 23)  # Friday, not a rule for every Friday.


def menu_url(slot='breakfast', day=DAY):
    return '/manage/dishes/?' + urlencode({'type': 'scheduled', 'meal': slot, 'date': day.isoformat()})


def picker_url(slot='breakfast', day=DAY):
    return '/manage/dishes/menu/?' + urlencode({'type': 'scheduled', 'meal': slot, 'date': day.isoformat()})


def ids(day, slot):
    return {entry.item.pk for entry in resolve_menu(day, slot)}


def test_saving_a_date_replaces_its_menu_without_changing_other_dates_meals_or_weekly_rows(grouped, kitchens):
    with tenant_context(kitchens[0]):
        before = list(MenuSchedule.objects.filter(mode='weekday').values_list('pk', 'weekday'))
        plan = save_daily_menu(slot=grouped['breakfast'], on_date=DAY, item_ids=[grouped['unassigned'].pk], revision=0)
        assert plan.revision == 1
        assert ids(DAY, grouped['breakfast']) == {grouped['unassigned'].pk}
        assert ids(DAY + timedelta(days=1), grouped['breakfast']) == {grouped['b'].pk, grouped['shared'].pk}
        assert ids(DAY + timedelta(days=7), grouped['breakfast']) == {grouped['b'].pk, grouped['shared'].pk}
        assert ids(DAY, grouped['dinner']) == {grouped['d'].pk, grouped['shared'].pk}
        assert list(MenuSchedule.objects.filter(mode='weekday').values_list('pk', 'weekday')) == before


def test_saving_an_empty_menu_never_falls_back_to_the_old_everyday_menu(grouped, kitchens):
    with tenant_context(kitchens[0]):
        save_daily_menu(slot=grouped['breakfast'], on_date=DAY, item_ids=[], revision=0)
        assert resolve_menu(DAY, grouped['breakfast']) == []
        assert ids(DAY + timedelta(days=1), grouped['breakfast'])


def test_date_removal_does_not_delete_product_disable_it_globally_or_change_another_meal(signed_in, grouped, kitchens):
    item = grouped['shared']
    target = menu_url()
    remove = f'/manage/dishes/{item.pk}/delete/?' + urlencode({'type': 'scheduled', 'meal': 'breakfast', 'date': DAY.isoformat(), 'next': target})
    page = signed_in.get(remove, HTTP_HOST=HOST)
    assert page.status_code == 200 and b'Remove from this menu?' in page.content
    assert b'permanently delete' not in page.content
    response = signed_in.post(remove, {'next': target, 'day_revision': 0}, HTTP_HOST=HOST)
    assert response['Location'] == target
    with tenant_context(kitchens[0]):
        item.refresh_from_db()
        assert item.active
        assert item.pk not in ids(DAY, grouped['breakfast'])
        assert item.pk in ids(DAY, grouped['dinner'])
        assert item.pk in ids(DAY + timedelta(days=1), grouped['breakfast'])


def test_daily_switch_is_explicit_and_repeated_stale_post_does_not_toggle_back(signed_in, grouped, kitchens):
    item = grouped['b']
    data = {'next': menu_url(), 'menu_date': DAY.isoformat(), 'menu_meal': 'breakfast', 'revision': '0', 'enabled': '0'}
    for _ in range(2):
        assert signed_in.post(f'/manage/dishes/{item.pk}/toggle/', data, HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchens[0]):
        assert item.pk not in ids(DAY, grouped['breakfast'])
        item.refresh_from_db()
        assert item.active
        assert MenuDay.objects.get(slot=grouped['breakfast'], on_date=DAY).revision == 1


def test_saving_date_preserves_existing_price_limits_and_sold_counts(grouped, kitchens):
    with tenant_context(kitchens[0]):
        row = MenuSchedule.objects.create(item=grouped['b'], slot=grouped['breakfast'], mode='date', on_date=DAY,
            price_override='119', qty_limit=10, qty_sold=4)
        save_daily_menu(slot=grouped['breakfast'], on_date=DAY, item_ids=[grouped['b'].pk], revision=0)
        row.refresh_from_db()
        assert (row.price_override, row.qty_limit, row.qty_sold) == (Decimal('119'), 10, 4)
        assert resolve_menu(DAY, grouped['breakfast'])[0].price == Decimal('119')


def test_removing_a_dish_from_the_day_also_blocks_server_order_pricing(grouped, kitchens):
    with tenant_context(kitchens[0]):
        save_daily_menu(slot=grouped['breakfast'], on_date=DAY, item_ids=[grouped['shared'].pk], revision=0)
        with pytest.raises(ItemNotOnMenu):
            price_lines([RequestedLine(grouped['b'].pk, 1)], delivery_date=DAY, slot=grouped['breakfast'])
        lines, subtotal = price_lines([RequestedLine(grouped['shared'].pk, 1)], delivery_date=DAY, slot=grouped['breakfast'])
        assert subtotal == Decimal('90')


def test_old_category_label_is_not_an_availability_rule_and_get_does_not_publish(signed_in, grouped, kitchens):
    with tenant_context(kitchens[0]):
        cat = grouped['b'].category
        cat.name = 'Tuesday Breakfast'
        cat.save()
        before = MenuSchedule.objects.count()
    page = signed_in.get(menu_url(), HTTP_HOST=HOST)
    assert page.status_code == 200 and b'Friday, 23 October 2026' in page.content
    assert b'Review this date' in page.content
    assert b'Tuesday Breakfast' not in page.content
    with tenant_context(kitchens[0]):
        assert not MenuDay.objects.exists()
        assert MenuSchedule.objects.count() == before


def test_staff_can_choose_existing_dishes_and_save_day_without_duplicate_products(signed_in, grouped, kitchens):
    with tenant_context(kitchens[0]):
        before = MenuItem.objects.count()
    page = signed_in.get(picker_url(), HTTP_HOST=HOST)
    assert page.status_code == 200
    assert set(page.context['form'].initial['items']) == {grouped['b'].pk, grouped['shared'].pk}
    assert grouped['shop'].pk not in page.context['form'].fields['items'].queryset.values_list('pk', flat=True)
    response = signed_in.post(picker_url(), {'items': [grouped['unassigned'].pk], 'revision': 0}, HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'] == menu_url()
    with tenant_context(kitchens[0]):
        assert MenuItem.objects.count() == before
        assert ids(DAY, grouped['breakfast']) == {grouped['unassigned'].pk}


def test_stale_menu_save_is_rejected_without_partial_changes(signed_in, grouped, kitchens):
    with tenant_context(kitchens[0]):
        save_daily_menu(slot=grouped['breakfast'], on_date=DAY, item_ids=[grouped['b'].pk], revision=0)
    page = signed_in.post(picker_url(), {'items': [grouped['shared'].pk], 'revision': 0}, HTTP_HOST=HOST)
    assert page.status_code == 200 and b'changed in another session' in page.content
    with tenant_context(kitchens[0]):
        assert ids(DAY, grouped['breakfast']) == {grouped['b'].pk}


def test_day_picker_refuses_shop_items_and_other_store_ids(signed_in, grouped, catalog, kitchens):
    for pk in [grouped['shop'].pk, catalog['theirs'].pk]:
        response = signed_in.post(picker_url(), {'items': [pk], 'revision': 0}, HTTP_HOST=HOST)
        assert response.status_code == 200 and response.context['form'].errors
    with tenant_context(kitchens[0]):
        assert not MenuDay.objects.exists()


def test_daily_menu_is_private_and_csrf_protected(client, owner, grouped):
    assert client.get(picker_url(), HTTP_HOST=HOST).status_code == 302
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(owner)
    assert strict.post(picker_url(), {'revision': 0}, HTTP_HOST=HOST).status_code == 403
    assert strict.get(picker_url(), HTTP_HOST=OTHER).status_code == 403


def test_date_form_prefills_one_day_and_adds_no_seven_day_recurrence(signed_in, grouped, kitchens):
    url = '/manage/dishes/new/?' + urlencode({'type': 'scheduled', 'meal': 'breakfast', 'date': DAY.isoformat(), 'next': menu_url()})
    page = signed_in.get(url, HTTP_HOST=HOST)
    assert page.context['form'].menu_date == DAY
    assert page.context['form']['slot'].value() == grouped['breakfast'].pk
    assert b'name="weekdays"' not in page.content
    response = signed_in.post(url, {'name': 'Friday only dish', 'fulfilment': 'scheduled', 'price': '70', 'category': '',
        'slot': grouped['breakfast'].pk, 'active': 'on', 'is_veg': 'on', 'sort': 0, 'day_available': 'on', 'day_revision': 0,
        'next': menu_url()}, HTTP_HOST=HOST)
    assert response.status_code == 302
    with tenant_context(kitchens[0]):
        item = MenuItem.objects.get(name='Friday only dish')
        assert not item.schedule.filter(mode='weekday').exists()
        assert item.pk in ids(DAY, grouped['breakfast'])
        assert item.pk not in ids(DAY + timedelta(days=1), grouped['breakfast'])


def test_invalid_dates_never_become_global_delete_or_other_day_mutations(signed_in, grouped, kitchens):
    for value in ['bad', '2026-02-30']:
        url = f'/manage/dishes/{grouped["b"].pk}/delete/?type=scheduled&meal=breakfast&date={value}'
        assert signed_in.post(url, HTTP_HOST=HOST).status_code == 404
    with tenant_context(kitchens[0]):
        assert MenuItem.objects.filter(pk=grouped['b'].pk).exists()
        assert not MenuDay.objects.exists()


def test_saved_empty_date_is_empty_in_management_and_offers_existing_dish_picker(signed_in, grouped, kitchens):
    with tenant_context(kitchens[0]):
        save_daily_menu(slot=grouped['breakfast'], on_date=DAY, item_ids=[], revision=0)
    page = signed_in.get(menu_url(), HTTP_HOST=HOST)
    assert page.status_code == 200 and page.context['rows'] == []
    assert b'No dishes selected for Friday, 23 October breakfast' in page.content
    assert page.context['menu_ui']['counts']['slots'][grouped['breakfast'].pk] == 0
    assert b'Choose dishes' in page.content
