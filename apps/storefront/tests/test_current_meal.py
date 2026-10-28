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
    (time(8, 59, 59), ['breakfast','lunch','dinner']), (time(9), ['lunch','dinner']),
    (time(14, 59, 59), ['lunch','dinner']), (time(15), ['dinner']),
    (time(19, 59, 59), ['dinner']), (time(20), []),
])
def test_each_food_category_respects_its_own_cutoff_for_combined_ordering(kitchen, menu, three_meals, clock, expected):
    now = timezone.make_aware(datetime.combine(menu['date'], clock))
    with tenant_context(kitchen):
        opened = [s.key for s in three_meals if customer_slot_is_open(s, menu['date'], now=now)]
        assert opened == expected
        assert all(customer_slot_is_open(s, menu['date'] + timedelta(days=1), now=now) for s in three_meals)
        assert not any(customer_slot_is_open(s, menu['date'] + timedelta(days=2), now=now) for s in three_meals)


@pytest.mark.parametrize('clock,allowed', [(time(8), {'breakfast','lunch','dinner'}), (time(12), {'lunch','dinner'}), (time(18), {'dinner'})])
def test_customer_can_choose_any_food_category_within_its_open_window(client, kitchen, menu, three_meals, clock, allowed):
    now = timezone.make_aware(datetime.combine(menu['date'], clock))
    with patch('django.utils.timezone.localtime', return_value=now):
        for slot in three_meals:
            client.post('/cart/clear/', HTTP_HOST=HOST)
            _add(client, menu, slot_key=slot.key)
            cart = client.get('/cart/', HTTP_HOST=HOST)
            assert (b'data-testid="cart-empty"' not in cart.content) == (slot.key in allowed)
            page = client.get('/menu/', {'slot': slot.key}, HTTP_HOST=HOST)
            assert (b'<input type="hidden" name="slot_key"' in page.content) == (slot.key in allowed)


@pytest.mark.parametrize('meal_key', ['breakfast', 'lunch', 'dinner'])
@pytest.mark.parametrize('payment_method', ['manual', 'online'])
def test_tomorrow_meals_can_be_ordered_today_with_delivery_in_payment_and_invoice(client, kitchen, menu, three_meals, meal_key, payment_method):
    from django.template.loader import render_to_string
    from apps.billing.services import confirm_payment, issue_bill
    from apps.payments.models import RazorpayConnection, PaymentIntent

    tomorrow = menu['date'] + timedelta(days=1)
    page = client.get('/menu/', {'date': tomorrow.isoformat(), 'slot': meal_key}, HTTP_HOST=HOST)
    assert b'Veg Meals' in page.content and b'btn-add' in page.content
    with tenant_context(kitchen):
        connection = RazorpayConnection(mode='test', key_id='rzp_test_Delivery', enabled=True)
        connection.key_secret = 'local-test-secret'
        connection.save()
        profile = kitchen.billing_profile
        profile.legal_name = 'Kitchen'
        profile.address = 'Chennai'
        profile.state = 'Tamil Nadu'
        profile.state_code = '33'
        profile.fssai_no = '12345678901234'
        profile.save()
    _add(client, menu, delta=2, slot_key=meal_key, delivery_date=tomorrow.isoformat())
    client.post('/cart/pincode/', {'pincode': '641001'}, HTTP_HOST=HOST)
    data = details(payment_method=payment_method)
    checked = review(client, data)
    assert checked.context['quote']['delivery_date'] == tomorrow
    assert checked.context['quote']['subtotal'] == Decimal('240')
    assert checked.context['quote']['delivery_fee'] == Decimal('20')
    assert checked.context['quote']['total'] == Decimal('260')
    assert b'Total to pay (including delivery)' in checked.content
    placed = client.post('/checkout/', placedata(checked, data), HTTP_HOST=HOST)
    assert placed.status_code == 302
    with tenant_context(kitchen):
        order = Order.objects.get()
        assert order.slot.key == meal_key and order.delivery_date == tomorrow
        assert order.delivery_fee == Decimal('20') and order.total == Decimal('260')
        if payment_method == 'online':
            assert PaymentIntent.objects.get(order=order).amount == 26000
            # Sandbox payments intentionally cannot issue real bills.
            return
        assert not PaymentIntent.objects.filter(order=order).exists()
        confirm_payment(order, actor='test:delivery-invoice')
        invoice = issue_bill(order)
        fee_lines = [line for line in invoice.lines if line['description'] == 'Delivery fee']
        assert len(fee_lines) == 1
        assert Decimal(fee_lines[0]['unit_price']) == Decimal('20')
        assert invoice.total == order.total == Decimal('260')
        assert sum(Decimal(line['taxable']) + Decimal(line['tax']) for line in invoice.lines) == invoice.total
        html = render_to_string('billing/_invoice_body.html', {'invoice': invoice})
        assert 'Delivery fee' in html and 'included in the total paid' in html


def test_switching_period_after_review_cannot_place_the_old_meal(client, kitchen, menu, three_meals):
    prepare(client, menu)
    post = placedata(review(client))
    later = timezone.make_aware(datetime.combine(menu['date'], time(15)))
    with patch('django.utils.timezone.localtime', return_value=later):
        response = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert response.status_code == 200 and b'Ordering is not open' in response.content
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
