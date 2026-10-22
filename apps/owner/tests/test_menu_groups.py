"""Annam edits one meal at a time without losing products or other schedules."""
from datetime import date
from urllib.parse import urlencode

import pytest

from apps.catalog.models import MenuItem, MenuCategory, MenuSchedule, Slot
from apps.tenancy.context import tenant_context
from .test_owner import kitchens, owner, signed_in, HOST, catalog


@pytest.fixture
def grouped(kitchens, catalog):
    with tenant_context(kitchens[0]):
        breakfast = Slot.objects.create(key='breakfast', label='Breakfast', order_cutoff='06:30', sort=0)
        lunch = catalog['slot']
        lunch.sort = 1
        lunch.save()
        dinner = Slot.objects.create(key='dinner', label='Dinner', order_cutoff='18:00', sort=2)
        meal_cat = MenuCategory.objects.create(name='Meals', slug='meals')
        b = MenuItem.objects.create(name='Breakfast Idly', price='110', category=meal_cat)
        l = MenuItem.objects.create(name='Lunch Rice', price='100', category=meal_cat)
        d = MenuItem.objects.create(name='Dinner Chapathi', price='80', category=meal_cat)
        shared = MenuItem.objects.create(name='Shared dish', price='90', category=meal_cat)
        unassigned = MenuItem.objects.create(name='Unassigned dish', price='50')
        for day in range(7):
            for item, slot in ((b, breakfast), (l, lunch), (d, dinner), (shared, breakfast), (shared, dinner)):
                MenuSchedule.objects.create(item=item, slot=slot, mode='weekday', weekday=day)
        # A dated override must not duplicate an item or hide it from its group.
        MenuSchedule.objects.create(item=b, slot=breakfast, mode='date', on_date=date(2026, 10, 22))
        return {'breakfast': breakfast, 'lunch': lunch, 'dinner': dinner, 'b': b, 'l': l, 'd': d,
                'shared': shared, 'unassigned': unassigned, 'shop': catalog['dish']}


def row_ids(response):
    return [row['obj'].pk for row in response.context['rows']]


def test_default_list_shows_breakfast_once_and_separates_other_items(signed_in, grouped):
    page = signed_in.get('/manage/dishes/', HTTP_HOST=HOST)
    assert page.status_code == 200
    assert set(row_ids(page)) == {grouped['b'].pk, grouped['shared'].pk}
    assert len(row_ids(page)) == 2
    assert page.context['menu_ui']['counts']['meals'] == 5
    assert page.context['menu_ui']['counts']['other'] == 1
    assert [tab['label'] for tab in page.context['menu_ui']['tabs']] == ['Breakfast', 'Lunch', 'Dinner', 'Not assigned']
    assert [tab['count'] for tab in page.context['menu_ui']['tabs']] == [2, 1, 2, 1]


@pytest.mark.parametrize(('meal', 'expected'), [('breakfast', ('b', 'shared')), ('lunch', ('l',)), ('dinner', ('d', 'shared')), ('unassigned', ('unassigned',))])
def test_each_meal_uses_saved_schedule_membership(signed_in, grouped, meal, expected):
    page = signed_in.get('/manage/dishes/', {'type': 'scheduled', 'meal': meal, 'date': 'all'}, HTTP_HOST=HOST)
    assert set(row_ids(page)) == {grouped[key].pk for key in expected}
    assert b'name="type" value="scheduled"' in page.content
    assert ('name="meal" value="' + meal + '"').encode() in page.content


def test_other_items_shows_only_shop_goods_and_relevant_categories(signed_in, grouped):
    page = signed_in.get('/manage/dishes/?type=courier', HTTP_HOST=HOST)
    assert row_ids(page) == [grouped['shop'].pk]
    assert page.context['add_label'] == 'Add item'
    filters = {f['param']: f for f in page.context['filters']}
    assert 'type' not in filters
    assert filters['category']['options'] == [(grouped['shop'].category_id, 'Podi')]


def test_search_status_and_pagination_keep_selected_group(signed_in, grouped, kitchens):
    with tenant_context(kitchens[0]):
        grouped['l'].active = False
        grouped['l'].save()
    page = signed_in.get('/manage/dishes/?type=scheduled&meal=lunch&q=Rice&status=0', HTTP_HOST=HOST)
    assert row_ids(page) == [grouped['l'].pk]
    assert 'meal=lunch' in page.context['rows'][0]['edit_url']
    assert 'status%3D0' in page.context['rows'][0]['edit_url']
    assert all('page=' not in tab['url'] for tab in page.context['menu_ui']['tabs'])


def test_disabled_and_dated_only_dishes_remain_manageable(signed_in, grouped, kitchens):
    with tenant_context(kitchens[0]):
        item = MenuItem.objects.create(name='Dated lunch', price='150', active=False)
        MenuSchedule.objects.create(item=item, slot=grouped['lunch'], mode='date', on_date=date(2026, 11, 1), available=False)
    page = signed_in.get('/manage/dishes/?meal=lunch&date=all', HTTP_HOST=HOST)
    assert set(row_ids(page)) == {grouped['l'].pk, item.pk}


def test_new_dish_prefills_the_selected_meal_and_other_item_type(signed_in, grouped):
    page = signed_in.get('/manage/dishes/new/?type=scheduled&meal=dinner&date=all', HTTP_HOST=HOST)
    assert page.context['form']['slot'].value() == grouped['dinner'].pk
    assert page.context['form']['fulfilment'].value() == 'scheduled'
    assert page.context['form']['weekdays'].value() == list(range(7))
    page = signed_in.get('/manage/dishes/new/?type=courier', HTTP_HOST=HOST)
    assert page.context['form']['fulfilment'].value() == 'courier'


def dish_data(item=None, **overrides):
    return {'name': item.name if item else 'New dinner meal', 'category': '', 'fulfilment': 'scheduled',
            'price': '125', 'description': '', 'active': 'on', 'is_veg': 'on', 'sort': '0',
            'weekdays': [0, 1, 2, 3, 4, 5, 6], **overrides}


def test_add_and_add_another_return_to_selected_meal(signed_in, grouped, kitchens):
    target = '/manage/dishes/?type=scheduled&meal=dinner'
    url = '/manage/dishes/new/?' + urlencode({'type': 'scheduled', 'meal': 'dinner', 'date': 'all', 'next': target})
    response = signed_in.post(url, dish_data(slot=grouped['dinner'].pk, next=target), HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'] == target
    with tenant_context(kitchens[0]):
        item = MenuItem.objects.get(name='New dinner meal')
        assert set(item.schedule.values_list('slot_id', flat=True)) == {grouped['dinner'].pk}
    response = signed_in.post(url, dish_data(name='Another dinner', slot=grouped['dinner'].pk, next=target, save_add=''), HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'].startswith('/manage/dishes/new/?')
    assert 'meal=dinner' in response['Location']


def test_editing_shared_breakfast_dish_preserves_its_dinner_and_dated_overrides(signed_in, grouped, kitchens):
    item = grouped['shared']
    with tenant_context(kitchens[0]):
        override = MenuSchedule.objects.create(item=item, slot=grouped['dinner'], mode='date', on_date=date(2026, 11, 3), price_override='95')
        dinner_rows = list(item.schedule.filter(slot=grouped['dinner']).values_list('pk', flat=True))
    target = '/manage/dishes/?type=scheduled&meal=breakfast'
    url = f'/manage/dishes/{item.pk}/?' + urlencode({'type': 'scheduled', 'meal': 'breakfast', 'date': 'all', 'next': target})
    page = signed_in.get(url, HTTP_HOST=HOST)
    assert page.context['form']['slot'].value() == grouped['breakfast'].pk
    response = signed_in.post(url, dish_data(item, slot=grouped['breakfast'].pk, weekdays=[0, 2], next=target), HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'] == target
    with tenant_context(kitchens[0]):
        assert sorted(item.schedule.filter(slot=grouped['breakfast']).values_list('weekday', flat=True)) == [0, 2]
        assert list(item.schedule.filter(slot=grouped['dinner']).values_list('pk', flat=True)) == dinner_rows
        override.refresh_from_db()
        assert str(override.price_override) == '95.00'


def test_delete_and_toggle_stay_in_selected_group(signed_in, grouped, kitchens):
    target = '/manage/dishes/?type=scheduled&meal=lunch'
    item = grouped['l']
    toggle = signed_in.post(f'/manage/dishes/{item.pk}/toggle/', {'next': target}, HTTP_HOST=HOST)
    assert toggle['Location'] == target
    page = signed_in.get(f'/manage/dishes/{item.pk}/delete/', {'next': target}, HTTP_HOST=HOST)
    assert page.status_code == 200 and page.context['return_url'] == target
    response = signed_in.post(f'/manage/dishes/{item.pk}/delete/', {'next': target}, HTTP_HOST=HOST)
    assert response['Location'] == target
    with tenant_context(kitchens[0]):
        assert not MenuItem.objects.filter(pk=item.pk).exists()


def test_bad_meal_values_and_empty_catalog_have_safe_defaults(signed_in, kitchens):
    page = signed_in.get('/manage/dishes/?meal=not-real&type=bad', HTTP_HOST=HOST)
    assert page.status_code == 200
    assert page.context['menu_ui']['selection']['meal'] == 'unassigned'
    assert not row_ids(page)
