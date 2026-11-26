"""Billing portal workflows and tenant boundaries."""
import pytest
from decimal import Decimal
from django.core import signing
from django.contrib.auth import get_user_model
from apps.owner.tests.test_owner import kitchens, owner, signed_in, _billing_data, HOST, OTHER
from apps.tenancy.context import tenant_context
from apps.tenancy.models import BillingProfile
from apps.catalog.models import MenuItem
from apps.orders.models import Order, Customer
from apps.billing.models import Invoice
from apps.delivery.models import DeliveryZone
from apps.billing.services import create_staff_order


@pytest.fixture
def item(kitchens):
    with tenant_context(kitchens[0]):
        return MenuItem.objects.create(name="Test Lunch", price="100", active=True)


def booking(tenant, item, channel="manual"):
    return {"token": signing.dumps({"tenant": tenant.pk, "key": "unique-test-booking"}, salt="staff-billing"),
            "channel": channel, "name": "Buyer", "phone": "919999999999", "address": "", "zone": "",
            "payment_mode": "manual", "lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "1", "lines-MAX_NUM_FORMS": "50",
            "lines-0-item": str(item.pk), "lines-0-meal": "lunch", "lines-0-quantity": "2", "unit_price": "0.01"}


def test_portal_requires_staff_and_stays_on_tenant_host(client, kitchens):
    r = client.get("/billing/", HTTP_HOST=HOST)
    assert r.status_code == 302 and r["Location"].startswith("/billing/login/")
    assert client.get("/billing/", HTTP_HOST="admin.localhost").status_code == 404
    user = get_user_model().objects.create_user("customer", password="test-only")
    client.force_login(user)
    assert client.get("/billing/", HTTP_HOST=HOST).status_code == 403


def test_portal_login_and_safe_redirect(client, owner):
    r = client.post("/billing/login/?next=https://evil.example/", {"username": "owner", "password": "pw-for-tests-only"}, HTTP_HOST=HOST)
    assert r.status_code == 302 and r["Location"] == "/billing/"


def test_manual_booking_payment_and_bill_remain_in_portal(signed_in, kitchens, item):
    for path in ("/billing/", "/billing/new/", "/billing/settings/", "/billing/manual/", "/billing/web/", "/billing/whatsapp/"):
        assert signed_in.get(path, HTTP_HOST=HOST).status_code == 200
    assert signed_in.post("/billing/settings/", _billing_data(), HTTP_HOST=HOST)["Location"] == "/billing/settings/"
    data = booking(kitchens[0], item)
    response = signed_in.post("/billing/new/", data, HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        order = Order.objects.get()
        assert order.total == Decimal("200")  # ignores client price
        assert order.channel == "manual"
        assert not Invoice.objects.exists()
    assert response["Location"] == f"/billing/orders/{order.pk}/"
    page = signed_in.get(response["Location"], HTTP_HOST=HOST)
    assert b"Test Lunch" in page.content and b"Confirm payment" in page.content
    signed_in.post("/billing/new/", data, HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        assert Order.objects.count() == 1
    signed_in.post(f"/billing/orders/{order.pk}/payment/", {}, HTTP_HOST=HOST)
    order.refresh_from_db()
    assert order.payment_status == "pending"
    response = signed_in.post(f"/billing/orders/{order.pk}/payment/", {"confirmed": "yes", "reference": "UTR 123"}, HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        invoice = Invoice.objects.get(order=order)
        assert invoice.payment_ref == "UTR 123"
    assert response["Location"] == f"/billing/bills/{invoice.pk}/"
    page = signed_in.get(response["Location"], HTTP_HOST=HOST)
    assert b"Print / Save as PDF" in page.content and b"Billing portal" in page.content
    assert f'/billing/orders/{order.pk}/'.encode() in page.content
    signed_in.post(f"/billing/orders/{order.pk}/bill/", HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        assert Invoice.objects.count() == 1


@pytest.mark.parametrize("channel", ["manual", "web", "whatsapp"])
def test_channel_sections_only_show_the_selected_source(signed_in, kitchens, item, channel):
    with tenant_context(kitchens[0]):
        customer = Customer.objects.create(phone="919888888888")
        for source in ("manual", "web", "whatsapp"):
            Order.objects.create(order_no=f"SOURCE-{source}", customer=customer, channel=source, subtotal="100", total="100")
    page = signed_in.get(f"/billing/{channel}/", HTTP_HOST=HOST)
    assert f"SOURCE-{channel}".encode() in page.content
    for other in {"manual", "web", "whatsapp"} - {channel}:
        assert f"SOURCE-{other}".encode() not in page.content
    assert signed_in.get("/billing/unknown/", HTTP_HOST=HOST).status_code == 404


def test_whatsapp_bookings_can_be_entered_without_an_automation_connection(signed_in, kitchens, item):
    r = signed_in.post("/billing/new/", booking(kitchens[0], item, "whatsapp"), HTTP_HOST=HOST)
    assert r.status_code == 302
    with tenant_context(kitchens[0]):
        order = Order.objects.get()
        assert order.channel == "whatsapp" and order.source == "wa_chat"


def test_foreign_items_and_form_tokens_are_rejected(signed_in, kitchens, item):
    with tenant_context(kitchens[1]):
        other = MenuItem.objects.create(name="Foreign Item", price="1")
    data = booking(kitchens[0], other)
    assert signed_in.post("/billing/new/", data, HTTP_HOST=HOST).status_code == 200
    data = booking(kitchens[1], item)
    assert signed_in.post("/billing/new/", data, HTTP_HOST=HOST).status_code == 200
    with tenant_context(kitchens[0]):
        assert not Order.objects.exists()


def test_foreign_orders_and_bills_are_not_accessible(signed_in, kitchens):
    from apps.billing.services import issue_bill
    with tenant_context(kitchens[1]):
        profile = BillingProfile.objects.get(tenant=kitchens[1])
        for key, value in _billing_data().items():
            if key not in ("round_total", "prices_include_tax", "delivery_fee_taxable"):
                setattr(profile, key, value)
        profile.save()
        customer = Customer.objects.create(phone="919888888888")
        order = Order.objects.create(order_no="PRIVATE", customer=customer, channel="manual", payment_status="paid", subtotal="100", total="100", items=[{"name":"Lunch", "quantity":1,"unit_price":"100","line_total":"100"}])
        invoice = issue_bill(order)
    assert signed_in.get(f"/billing/orders/{order.pk}/", HTTP_HOST=HOST).status_code == 404
    assert signed_in.get(f"/billing/bills/{invoice.pk}/", HTTP_HOST=HOST).status_code == 404
    for action in ("payment", "bill"):
        assert signed_in.post(f"/billing/orders/{order.pk}/{action}/", {"confirmed":"yes"}, HTTP_HOST=HOST).status_code == 404
    assert signed_in.get("/billing/", HTTP_HOST=OTHER).status_code == 403


def test_delivery_fee_minimum_and_unpaid_bill_rule(signed_in, kitchens, item):
    with tenant_context(kitchens[0]):
        zone = DeliveryZone.objects.create(area_name="Test Area", pincode="641001", delivery_fee="30", min_order="150")
    data = booking(kitchens[0], item)
    data.update(zone=str(zone.pk), address="Delivery Street", payment_mode="cod")
    data["lines-0-quantity"] = "1"
    assert signed_in.post("/billing/new/", data, HTTP_HOST=HOST).status_code == 200
    data["lines-0-quantity"] = "2"
    assert signed_in.post("/billing/new/", data, HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchens[0]):
        order = Order.objects.get()
        assert order.total == Decimal("230") and order.payment_status == "cod_pending"
    signed_in.post(f"/billing/orders/{order.pk}/bill/", HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        assert not Invoice.objects.exists()
    assert signed_in.get(f"/billing/orders/{order.pk}/payment/", HTTP_HOST=HOST).status_code == 405


def test_booking_picker_groups_items_by_meal_and_keeps_prices_tenant_scoped(signed_in, kitchens, item):
    from datetime import time
    from apps.catalog.models import Slot, MenuSchedule
    from apps.billing.services import staff_catalog
    with tenant_context(kitchens[0]):
        breakfast = Slot.objects.create(key="breakfast", label="Breakfast", order_cutoff=time(9))
        dinner = Slot.objects.create(key="dinner", label="Dinner", order_cutoff=time(19))
        for slot in (breakfast, dinner):
            MenuSchedule.objects.create(item=item, slot=slot, mode="weekday", weekday=0)
        other = MenuItem.objects.create(name="Test Pickle", price="50", fulfilment="courier")
        inactive = MenuItem.objects.create(name="Not For Sale", price="1", active=False)
        catalog = staff_catalog()
        assert next(x for x in catalog if x["id"] == item.pk)["groups"] == ["breakfast", "dinner"]
        assert next(x for x in catalog if x["id"] == other.pk)["groups"] == ["snacks"]
        assert inactive.pk not in {x["id"] for x in catalog}
    with tenant_context(kitchens[1]):
        MenuItem.objects.create(name="Private Rival Dish", price="99")
    response = signed_in.get("/billing/new/", HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b'optgroup label="Breakfast"' in response.content
    assert b'optgroup label="Dinner"' in response.content
    assert b'optgroup label="Snacks"' in response.content
    assert b'Private Rival Dish' not in response.content
    assert b'Not For Sale' not in response.content
    assert b'100.00' in response.content
    assert response.context['lines'].total_form_count() == 1


def test_item_selection_infers_its_single_meal_without_a_second_category_field(signed_in, kitchens, item):
    from apps.catalog.models import Slot, MenuSchedule
    with tenant_context(kitchens[0]):
        slot = Slot.objects.create(key='lunch', label='Lunch', order_cutoff='23:59')
        MenuSchedule.objects.create(item=item, slot=slot, mode='weekday', weekday=0)
    page = signed_in.get('/billing/new/', HTTP_HOST=HOST)
    assert b'>Food category</label>' not in page.content
    data = booking(kitchens[0], item)
    data.pop('lines-0-meal')
    response = signed_in.post('/billing/new/', data, HTTP_HOST=HOST)
    assert response.status_code == 302
    with tenant_context(kitchens[0]):
        order = Order.objects.get()
        assert order.items[0]['meal_key'] == 'lunch'
        assert order.total == Decimal('200')


def test_hidden_meal_value_cannot_override_the_selected_items_actual_meal(signed_in, kitchens, item):
    from apps.catalog.models import Slot, MenuSchedule
    with tenant_context(kitchens[0]):
        slot = Slot.objects.create(key='lunch', label='Lunch', order_cutoff='23:59')
        MenuSchedule.objects.create(item=item, slot=slot, mode='weekday', weekday=0)
    data = booking(kitchens[0], item)
    data['lines-0-meal'] = 'dinner'
    response = signed_in.post('/billing/new/', data, HTTP_HOST=HOST)
    assert response.status_code == 200
    with tenant_context(kitchens[0]):
        assert not Order.objects.exists()


def test_collect_on_delivery_stays_unpaid_after_delivery_until_money_is_confirmed(signed_in, kitchens, item):
    from apps.orders.services import advance_status
    from apps.orders.models import OrderEvent
    signed_in.post('/billing/settings/', _billing_data(), HTTP_HOST=HOST)
    response = signed_in.post('/billing/new/', booking(kitchens[0], item), HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        order = Order.objects.get()
    for _ in range(2):
        assert signed_in.post(f'/billing/orders/{order.pk}/payment/', {'action':'collect_on_delivery'}, HTTP_HOST=HOST).status_code == 302
    with tenant_context(kitchens[0]):
        order.refresh_from_db()
        assert order.payment_mode == 'cod' and order.payment_status == 'cod_pending'
        assert OrderEvent.objects.filter(order=order,note__startswith='Payment not received.').count() == 1
        for status in ['confirmed','preparing','out_for_delivery','delivered']:
            order = advance_status(order,status,actor='test-owner')
        assert order.payment_status == 'cod_pending' and not Invoice.objects.exists()
    response = signed_in.post(f'/billing/orders/{order.pk}/payment/', {'confirmed':'yes','reference':'cash-collected'}, HTTP_HOST=HOST)
    assert response.status_code == 302
    with tenant_context(kitchens[0]):
        order.refresh_from_db()
        assert order.payment_status == 'paid' and Invoice.objects.filter(order=order).count() == 1
    signed_in.post(f'/billing/orders/{order.pk}/payment/', {'action':'collect_on_delivery'}, HTTP_HOST=HOST)
    order.refresh_from_db()
    assert order.payment_status == 'paid'


def test_website_order_cannot_use_staff_collect_on_delivery_action(signed_in, kitchens, item):
    signed_in.post('/billing/new/', booking(kitchens[0], item), HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        order=Order.objects.get()
        order.channel='web';order.payment_mode='online';order.save(update_fields=['channel','payment_mode'])
    signed_in.post(f'/billing/orders/{order.pk}/payment/', {'action':'collect_on_delivery'}, HTTP_HOST=HOST)
    order.refresh_from_db()
    assert order.payment_mode == 'online' and order.payment_status == 'pending'



def test_manual_payment_website_order_can_be_marked_for_collection(signed_in, kitchens, item):
    signed_in.post('/billing/new/', booking(kitchens[0], item), HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        order=Order.objects.get();order.channel='web';order.save(update_fields=['channel'])
    page=signed_in.get(f'/billing/orders/{order.pk}/',HTTP_HOST=HOST)
    assert b'Cash on delivery' in page.content and b'value="collect_on_delivery"' in page.content
    signed_in.post(f'/billing/orders/{order.pk}/payment/',{'action':'collect_on_delivery'},HTTP_HOST=HOST)
    order.refresh_from_db()
    assert order.payment_mode=='cod' and order.payment_status=='cod_pending' and order.status=='placed'
    with tenant_context(kitchens[0]):assert not Invoice.objects.exists()


def test_online_website_without_intent_still_cannot_be_manually_settled(signed_in, kitchens, item):
    signed_in.post('/billing/new/', booking(kitchens[0], item), HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        order=Order.objects.get();order.channel='web';order.payment_mode='online';order.save(update_fields=['channel','payment_mode'])
    page=signed_in.get(f'/billing/orders/{order.pk}/',HTTP_HOST=HOST)
    assert b'Payment not received' in page.content and b'value="collect_on_delivery"' not in page.content
    signed_in.post(f'/billing/orders/{order.pk}/payment/',{'confirmed':'yes'},HTTP_HOST=HOST)
    order.refresh_from_db();assert order.payment_status=='pending'
    for status, payment in [('cancelled','pending'),('placed','refunded')]:
        order.status=status;order.payment_status=payment;order.save(update_fields=['status','payment_status'])
        page=signed_in.get(f'/billing/orders/{order.pk}/',HTTP_HOST=HOST)
        assert b'Awaiting verified online payment' not in page.content


def test_unpaid_bill_then_collection_reuses_number(signed_in, kitchens, item):
    from apps.billing.presentation import receipt_details
    signed_in.post('/billing/settings/', _billing_data(), HTTP_HOST=HOST)
    signed_in.post('/billing/new/', booking(kitchens[0], item), HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        order = Order.objects.get()
    path = f'/billing/orders/{order.pk}/'
    response = signed_in.post(path+'bill/', {'issue_unpaid':'yes'}, HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        invoice = Invoice.objects.get(order=order)
        number, buyer = invoice.number, dict(invoice.buyer)
        assert receipt_details(invoice)['amount_due'] == order.total
    order.refresh_from_db()
    assert order.payment_status == 'pending'
    assert b'UNPAID' in signed_in.get(response['Location'], HTTP_HOST=HOST).content
    assert b'Confirm payment received' in signed_in.get(path, HTTP_HOST=HOST).content
    signed_in.post(path+'bill/', {'issue_unpaid':'yes'}, HTTP_HOST=HOST)
    signed_in.post(path+'payment/', {'action':'collect_on_delivery'}, HTTP_HOST=HOST)
    signed_in.post(path+'payment/', {'confirmed':'yes','reference':'CASH-COLLECTED'}, HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        assert Invoice.objects.filter(order=order).count() == 1
        invoice.refresh_from_db()
        assert invoice.number == number and invoice.buyer == buyer
        state = receipt_details(invoice)
        assert state['payment_received'] and state['amount_due'] == 0
        assert state['settlement_reference'] == 'CASH-COLLECTED'
