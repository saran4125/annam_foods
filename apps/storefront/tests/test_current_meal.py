"""Website customers order only the current meal, at the displayed delivery fee."""
from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.catalog.models import MenuSchedule, Slot
from apps.catalog.services import customer_slot_is_open
from apps.orders.models import Order
from apps.tenancy.context import tenant_context
from .test_storefront import HOST, kitchen, menu, _add
from .test_checkout import details, review, placedata, prepare


@pytest.fixture
def three_meals(kitchen, menu):
    with tenant_context(kitchen):
        breakfast = Slot.objects.create(key='breakfast', label='Breakfast', order_cutoff=time(9), sort=9)
        dinner = Slot.objects.create(key='dinner', label='Dinner', order_cutoff=time(20), sort=0)
        for slot in (breakfast, dinner):
            for day in (menu['date'], menu['date'] + timedelta(days=1)):
                MenuSchedule.objects.create(item=menu['item'], slot=slot, mode='date', on_date=day)
        MenuSchedule.objects.create(item=menu['item'], slot=menu['slot'], mode='date',
                                    on_date=menu['date'] + timedelta(days=1))
    return breakfast, menu['slot'], dinner


@pytest.mark.parametrize('clock,expected', [
    (time(8, 59, 59), 'breakfast'), (time(9), 'lunch'),
    (time(14, 59, 59), 'lunch'), (time(15), 'dinner'),
    (time(19, 59, 59), 'dinner'), (time(20), None),
])
def test_only_one_meal_is_open_at_each_cutoff_regardless_of_display_order(kitchen, menu, three_meals, clock, expected):
    now = timezone.make_aware(datetime.combine(menu['date'], clock))
    with tenant_context(kitchen):
        opened = [s.key for s in three_meals if customer_slot_is_open(s, menu['date'], now=now)]
        assert opened == ([expected] if expected else [])
        assert not any(customer_slot_is_open(s, menu['date'] + timedelta(days=1), now=now) for s in three_meals)


@pytest.mark.parametrize('clock,allowed', [(time(8), 'breakfast'), (time(12), 'lunch'), (time(18), 'dinner')])
def test_customer_cannot_add_another_meal_even_to_an_empty_cart(client, kitchen, menu, three_meals, clock, allowed):
    now = timezone.make_aware(datetime.combine(menu['date'], clock))
    with patch('django.utils.timezone.localtime', return_value=now):
        for slot in three_meals:
            client.post('/cart/clear/', HTTP_HOST=HOST)
            _add(client, menu, slot_key=slot.key)
            cart = client.get('/cart/', HTTP_HOST=HOST)
            assert (b'data-testid="cart-empty"' not in cart.content) == (slot.key == allowed)
            page = client.get('/menu/', {'slot': slot.key}, HTTP_HOST=HOST)
            assert (b'<input type="hidden" name="slot_key"' in page.content) == (slot.key == allowed)


def test_tomorrow_menu_is_visible_but_cannot_be_added(client, kitchen, menu, three_meals):
    tomorrow = menu['date'] + timedelta(days=1)
    page = client.get('/menu/', {'date': tomorrow.isoformat(), 'slot': 'lunch'}, HTTP_HOST=HOST)
    assert b'Veg Meals' in page.content and b'btn-add' not in page.content
    _add(client, menu, delivery_date=tomorrow.isoformat())
    assert b'data-testid="cart-empty"' in client.get('/cart/', HTTP_HOST=HOST).content


def test_switching_period_after_review_cannot_place_the_old_meal(client, kitchen, menu, three_meals):
    prepare(client, menu)
    post = placedata(review(client))
    later = timezone.make_aware(datetime.combine(menu['date'], time(15)))
    with patch('django.utils.timezone.localtime', return_value=later):
        response = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert response.status_code == 200 and b'not accepting orders now' in response.content
    with tenant_context(kitchen):
        assert not Order.objects.exists()


def test_delivery_charge_is_visible_before_and_after_order_and_preserved_on_receipt(client, kitchen, menu):
    _add(client, menu, delta=2)
    cart = client.get('/cart/', HTTP_HOST=HOST)
    assert b'Delivery charge' in cart.content and b'Enter delivery pincode' in cart.content
    client.post('/cart/pincode/', {'pincode': '641001'}, HTTP_HOST=HOST)
    cart = client.get('/cart/', HTTP_HOST=HOST)
    assert b'data-testid="delivery-charge"' in cart.content and b'20' in cart.content
    page = client.get('/checkout/', HTTP_HOST=HOST)
    assert page.context['cart_totals']['delivery_fee'] == Decimal('20')
    assert b'Delivery charge' in page.content
    checked = review(client, details())
    assert checked.context['quote']['delivery_fee'] == Decimal('20')
    assert b'Delivery charge' in checked.content
    placed = client.post('/checkout/', placedata(checked), HTTP_HOST=HOST)
    with tenant_context(kitchen):
        from apps.delivery.models import DeliveryZone
        DeliveryZone.objects.update(delivery_fee=99)
    receipt = client.get(placed['Location'], HTTP_HOST=HOST)
    assert receipt.context['order'].delivery_fee == Decimal('20')
    assert receipt.context['order'].total == Decimal('260')
    assert b'Delivery charge' in receipt.content
