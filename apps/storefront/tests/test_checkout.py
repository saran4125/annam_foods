"""Real orders only for covered addresses, at live prices, once per review."""
from decimal import Decimal
from django.test import Client
from django.contrib.auth import get_user_model
import pytest

from apps.catalog.models import MenuItem, MenuSchedule
from apps.delivery.models import DeliveryZone
from apps.orders.models import Order, OrderEvent, PaymentStatus, Channel
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantDomain, TenantStatus, TenantConfig, TenantUser
from .test_storefront import HOST, kitchen, menu, _add


def details(**overrides):
    return {'name': 'Customer One', 'phone': '9876543210', 'email': 'buyer@example.test',
            'pincode': '641001', 'line1': '12 Kitchen Road', 'line2': 'RS Puram',
            'city': 'Coimbatore', 'landmark': '', 'zone_id': '', **overrides}


def review(client, data=None):
    return client.post('/checkout/', {'action': 'review', **(data or details())}, HTTP_HOST=HOST)


def placedata(response, data=None):
    return {**(data or details()), 'action': 'place', 'checkout_token': response.context['checkout_token']}


def prepare(client, menu):
    _add(client, menu, delta=2)
    client.post('/cart/pincode/', {'pincode': '641001'}, HTTP_HOST=HOST)


def test_meal_checkout_creates_one_unpaid_website_order_and_private_confirmation(client, kitchen, menu):
    prepare(client, menu)
    assert b'href="/checkout/"' in client.get('/cart/', HTTP_HOST=HOST).content
    page = review(client)
    assert page.status_code == 200 and page.context['quote']['total'] == Decimal('260')
    response = client.post('/checkout/', placedata(page), HTTP_HOST=HOST)
    assert response.status_code == 302
    with tenant_context(kitchen):
        order = Order.objects.get()
        assert order.channel == Channel.WEB and order.source == 'storefront'
        assert order.payment_status == PaymentStatus.PENDING
        assert order.payment_mode == 'manual' and order.total == Decimal('260')
        assert order.address['recipient_name'] == 'Customer One'
        assert order.address['pincode'] == '641001'
        assert OrderEvent.objects.filter(order=order).count() == 1
    receipt = client.get(response['Location'], HTTP_HOST=HOST)
    assert order.order_no.encode() in receipt.content
    assert 'no-store' in receipt['Cache-Control']
    assert Client().get(response['Location'], HTTP_HOST=HOST).status_code == 404
    assert b'data-testid="cart-empty"' in client.get('/cart/', HTTP_HOST=HOST).content


def test_double_submit_and_refresh_return_the_same_order_without_clearing_a_new_cart(client, kitchen, menu):
    prepare(client, menu)
    post = placedata(review(client))
    first = client.post('/checkout/', post, HTTP_HOST=HOST)
    _add(client, menu)
    second = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert first.status_code == second.status_code == 302 and first['Location'] == second['Location']
    with tenant_context(kitchen):
        assert Order.objects.count() == 1 and OrderEvent.objects.count() == 1
    assert client.session[f'cart.{kitchen.pk}']['items'][str(menu['item'].pk)] == 1


@pytest.mark.parametrize('pin', ['', '123', '600001', '110001'])
def test_meal_checkout_never_accepts_an_out_of_zone_or_missing_pincode(client, kitchen, menu, pin):
    prepare(client, menu)
    response = review(client, details(pincode=pin))
    assert 'checkout_token' not in response.context
    with tenant_context(kitchen):
        assert Order.objects.count() == 0


def test_changing_to_an_unsupported_pincode_after_review_cannot_place_an_order(client, kitchen, menu):
    prepare(client, menu)
    post = placedata(review(client))
    post['pincode'] = '110001'
    response = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b"deliver meals to this pincode" in response.content
    with tenant_context(kitchen):
        assert Order.objects.count() == 0


@pytest.mark.parametrize('change', ['price', 'fee', 'sold_out', 'paused', 'zone_removed', 'slot_inactive', 'holiday'])
def test_placing_rechecks_prices_menu_and_delivery_rules_after_review(client, kitchen, menu, change):
    prepare(client, menu)
    post = placedata(review(client))
    with tenant_context(kitchen):
        if change == 'price':
            MenuItem.objects.filter(pk=menu['item'].pk).update(price=Decimal('150'))
        elif change == 'fee':
            DeliveryZone.objects.update(delivery_fee=Decimal('99'))
        elif change == 'sold_out':
            MenuSchedule.objects.update(available=False)
        elif change == 'paused':
            TenantConfig.objects.filter(tenant=kitchen).update(features={'website_ordering': False})
        elif change == 'zone_removed':
            DeliveryZone.objects.update(active=False)
        elif change == 'slot_inactive':
            menu['slot'].active = False
            menu['slot'].save()
        elif change == 'holiday':
            TenantConfig.objects.filter(tenant=kitchen).update(checkout_settings={'closed_dates': [menu['date'].isoformat()]})
    response = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert response.status_code == 200 and response.context['form'].non_field_errors()
    with tenant_context(kitchen):
        assert Order.objects.count() == 0


def test_repeated_area_pincodes_require_an_explicit_served_area(client, kitchen, menu):
    prepare(client, menu)
    with tenant_context(kitchen):
        other = DeliveryZone.objects.create(pincode='641001', area_name='Second area', delivery_fee=45)
    response = review(client)
    assert response.context['form'].errors.get('zone_id')
    response = review(client, details(zone_id=str(other.pk)))
    assert response.context['quote']['delivery_fee'] == Decimal('45')


def test_meal_minimum_and_cutoff_are_enforced_at_checkout(client, kitchen, menu):
    _add(client, menu)
    response = review(client)
    assert b'minimum' in response.content or b'subtotal' in response.content
    menu['slot'].order_cutoff = __import__('datetime').time(10)
    menu['slot'].save()
    response = review(client)
    assert b'Ordering is not open' in response.content
    with tenant_context(kitchen):
        assert not Order.objects.exists()


def test_checkout_token_is_bound_to_tenant_browser_and_the_reviewed_contents(client, kitchen, menu):
    prepare(client, menu)
    post = placedata(review(client))
    intruder = Client()
    prepare(intruder, menu)
    assert intruder.post('/checkout/', post, HTTP_HOST=HOST).status_code == 200
    assert client.post('/checkout/', {**post, 'checkout_token': post['checkout_token'] + 'tampered'}, HTTP_HOST=HOST).status_code == 200
    assert client.post('/checkout/', {**post, 'name': 'Another person'}, HTTP_HOST=HOST).status_code == 200
    with tenant_context(kitchen):
        assert not Order.objects.exists()


def test_checkout_ignores_client_prices_and_payment_claims(client, kitchen, menu):
    prepare(client, menu)
    response = review(client, details(total='1', payment_status='paid'))
    assert response.context['quote']['total'] == Decimal('260')
    post = placedata(response)
    post.update(total='1', delivery_fee='0', payment_status='paid')
    assert client.post('/checkout/', post, HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchen):
        order = Order.objects.get()
        assert order.total == Decimal('260') and order.payment_status == 'pending'


def test_shop_checkout_uses_local_area_fee_or_defers_outside_chennai_courier(client, kitchen, menu):
    TenantConfig.objects.filter(tenant=kitchen).update(features={'snacks_courier': True}, checkout_settings={
        'courier_enabled': True, 'courier_fee': '55', 'courier_minimum': '100'})
    with tenant_context(kitchen):
        item = MenuItem.objects.create(name='Podi', fulfilment='courier', price=150)
    client.post('/cart/add/', {'kind': 'shop', 'item_id': item.pk}, HTTP_HOST=HOST)
    outside = review(client, details(state='Karnataka',city='Bengaluru',pincode='560001'))
    assert outside.context['quote']['courier_deferred']
    assert outside.context['quote']['total'] == Decimal('150')
    response = review(client, details(pincode='641001', city='Chennai'))
    assert response.context['quote']['total'] == Decimal('170')
    assert response.context['quote']['slot'] is None
    assert client.post('/checkout/', placedata(response, details(pincode='641001',city='Chennai')), HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchen):
        order = Order.objects.get()
        assert order.fulfilment == 'courier' and order.slot is None and order.delivery_date is None
        assert order.delivery_fee == Decimal('20')


def test_unconfigured_courier_delivery_fails_closed(client, kitchen, menu):
    TenantConfig.objects.filter(tenant=kitchen).update(features={'snacks_courier': True})
    with tenant_context(kitchen):
        item = MenuItem.objects.create(name='Podi', fulfilment='courier', price=150)
    client.post('/cart/add/', {'kind': 'shop', 'item_id': item.pk}, HTTP_HOST=HOST)
    assert 'checkout_token' not in review(client).context
    client.post('/cart/pincode/', {'pincode': '641001'}, HTTP_HOST=HOST)
    assert b'data-blocked="delivery"' in client.get('/cart/', HTTP_HOST=HOST).content


def test_tax_exclusive_checkout_and_bill_share_frozen_tax_rates(client, kitchen, menu):
    from apps.billing.services import confirm_payment, issue_bill
    from apps.orders.models import Customer
    with tenant_context(kitchen):
        Customer.objects.create(phone='919876543210', name='Original customer', gstin='PRIVATE-GST', business_name='Private business')
    profile = kitchen.billing_profile
    profile.legal_name = 'Test Kitchen'
    profile.address = 'Tamil Nadu'
    profile.fssai_no = '12345678901234'
    profile.gst_mode = 'regular'
    profile.gstin = '33ABCDE1234F1Z5'
    profile.state = 'Tamil Nadu'
    profile.state_code = '33'
    profile.prices_include_tax = False
    profile.tax_rate = 5
    profile.save()
    prepare(client, menu)
    response = review(client)
    assert response.context['quote']['total'] == Decimal('273')
    assert response.context['quote']['extra_tax'] == Decimal('13')
    assert client.post('/checkout/', placedata(response), HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchen):
        order = Order.objects.get()
        profile.tax_rate = 18
        profile.save()
        MenuItem.objects.filter(pk=menu['item'].pk).update(tax_rate=28)
        confirm_payment(order, actor='owner:test')
        invoice = issue_bill(order)
        assert invoice.total == Decimal('273')
        assert invoice.buyer['gstin'] == '' and invoice.buyer['business_name'] == ''
        assert order.buyer_name == 'Customer One'


def test_guest_order_does_not_expose_existing_customers_name_or_address(client, kitchen, menu):
    from apps.orders.models import Customer
    with tenant_context(kitchen):
        Customer.objects.create(phone='919876543210', name='Private previous customer', billing_address='Private address')
    prepare(client, menu)
    placed = client.post('/checkout/', placedata(review(client)), HTTP_HOST=HOST)
    receipt = client.get(placed['Location'], HTTP_HOST=HOST)
    assert b'Private previous customer' not in receipt.content and b'Private address' not in receipt.content
    assert b'Customer One' in receipt.content


def test_checkout_requires_csrf_and_reading_does_not_create_an_order(kitchen, menu):
    client = Client(enforce_csrf_checks=True)
    assert client.post('/checkout/', details(), HTTP_HOST=HOST).status_code == 403
    assert client.get('/checkout/', HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchen):
        assert not Order.objects.exists()


def test_checkout_token_and_confirmation_cannot_cross_tenants(client, kitchen, menu):
    prepare(client, menu)
    post = placedata(review(client))
    first = client.post('/checkout/', post, HTTP_HOST=HOST)
    other = Tenant.objects.create(slug='other', name='Other', status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=other, hostname='other.localhost', is_primary=True)
    assert client.get(first['Location'], HTTP_HOST='other.localhost').status_code == 404
    assert client.post('/checkout/', post, HTTP_HOST='other.localhost').status_code == 200
    with tenant_context(other):
        assert Order.objects.count() == 0


def test_order_review_expires_and_cart_quantity_changes_require_new_review(client, kitchen, menu):
    from unittest.mock import patch
    prepare(client, menu)
    response = review(client)
    post = placedata(response)
    with patch('django.core.signing.time.time', return_value=__import__('time').time() + 1900):
        expired = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert b'expired' in expired.content
    _add(client, menu)
    changed = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert b'changed' in changed.content
    with tenant_context(kitchen):
        assert not Order.objects.exists()


def test_meal_checkout_rejects_tampered_far_future_dates(client, kitchen, menu):
    from datetime import timedelta
    prepare(client, menu)
    session = client.session
    session[f'cart.{kitchen.pk}']['delivery_date'] = (menu['date'] + timedelta(days=20)).isoformat()
    session.save()
    response = review(client)
    assert 'checkout_token' not in response.context


def test_checkout_settings_are_owner_scoped_and_no_longer_need_a_pincode_list(client, kitchen, menu):
    user = get_user_model().objects.create_user(username='checkout-owner')
    TenantUser.all_tenants.create(tenant=kitchen, user=user, role='owner')
    client.force_login(user)
    response = client.post('/manage/checkout-settings/', {
        'courier_enabled': 'on', 'courier_pincodes': '', 'courier_fee': '25', 'courier_minimum': '100'}, HTTP_HOST=HOST)
    assert response.status_code == 302
    page = client.get('/manage/checkout-settings/', HTTP_HOST=HOST)
    assert b'courier_pincodes' not in page.content
    assert b'courier-pincodes.js' not in page.content
    response = client.post('/manage/checkout-settings/', {
        'courier_enabled': 'on', 'courier_pincodes': '600005\n641001', 'courier_fee': '25', 'courier_minimum': '100',
        'closed_dates': '2026-11-01', 'payment_instructions': 'Contact the kitchen to arrange payment.'}, HTTP_HOST=HOST)
    assert response.status_code == 302
    settings = TenantConfig.objects.get(tenant=kitchen).checkout_settings
    assert 'courier_pincodes' not in settings
    assert settings['courier_fee'] == '25' and settings['closed_dates'] == ['2026-11-01']
    other = Tenant.objects.create(slug='other', name='Other', status=TenantStatus.ACTIVE)
    TenantDomain.objects.create(tenant=other, hostname='other.localhost', is_primary=True)
    assert client.get('/manage/checkout-settings/', HTTP_HOST='other.localhost').status_code == 403
    assert not TenantConfig.objects.get(tenant=other).checkout_settings


def test_courier_settings_with_missing_charge_fail_closed(kitchen, menu):
    from apps.delivery.checkout import courier_quote
    config = kitchen.config
    config.checkout_settings = {'courier_enabled': True, 'courier_pincodes': ['641001']}
    config.save()
    assert courier_quote(kitchen, '641001') is None


def test_website_order_appears_in_admin_and_website_billing(client, kitchen, menu):
    prepare(client, menu)
    assert client.post('/checkout/', placedata(review(client)), HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchen):
        number = Order.objects.get().order_no
    user = get_user_model().objects.create_user(username='order-reviewer')
    TenantUser.all_tenants.create(tenant=kitchen, user=user, role='owner')
    client.force_login(user)
    assert number.encode() in client.get('/manage/orders/', HTTP_HOST=HOST).content
    # Billing keeps its own staff login policy; the same tenant order book is used.
    with tenant_context(kitchen):
        assert Order.objects.filter(channel='web', order_no=number).exists()


@pytest.mark.parametrize('pin', ['', '625001'])
def test_shop_checkout_places_order_without_any_pincode_whitelist(client, kitchen, menu, pin):
    TenantConfig.objects.filter(tenant=kitchen).update(features={'snacks_courier': True}, checkout_settings={
        'courier_enabled': True, 'courier_fee': '55', 'courier_minimum': '100'})
    with tenant_context(kitchen):
        item = MenuItem.objects.create(name='Podi', fulfilment='courier', price=150)
    client.post('/cart/add/', {'kind': 'shop', 'item_id': item.pk}, HTTP_HOST=HOST)
    cart = client.get('/cart/', HTTP_HOST=HOST)
    assert b'href="/checkout/"' in cart.content
    assert b'aria-label="Delivery pincode"' not in cart.content
    data = details(pincode=pin, city='Madurai')
    response = review(client, data)
    assert response.context['quote']['total'] == Decimal('150')
    post = placedata(response, data)
    first = client.post('/checkout/', post, HTTP_HOST=HOST)
    assert first.status_code == 302
    assert client.post('/checkout/', post, HTTP_HOST=HOST)['Location'] == first['Location']
    with tenant_context(kitchen):
        order = Order.objects.get()
        assert order.address['pincode'] == pin
        assert order.address['city'] == 'Madurai' and order.address['state'] == 'Tamil Nadu'
        assert order.delivery_fee == Decimal('0') and order.total == Decimal('150')


def test_shop_minimum_is_still_checked_without_a_pincode(client, kitchen, menu):
    TenantConfig.objects.filter(tenant=kitchen).update(features={'snacks_courier': True}, checkout_settings={
        'courier_enabled': True, 'courier_fee': '55', 'courier_minimum': '200'})
    with tenant_context(kitchen):
        item = MenuItem.objects.create(name='Podi', fulfilment='courier', price=150)
    client.post('/cart/add/', {'kind': 'shop', 'item_id': item.pk}, HTTP_HOST=HOST)
    response = review(client, details(pincode=''))
    assert 'checkout_token' not in response.context
    assert b'Add' in response.content and b'50.00 more' in response.content
