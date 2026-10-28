"""Customer-approved combined meals, one delivery fee, courier receivables and reports."""
from datetime import datetime,time,timedelta
from decimal import Decimal
from unittest.mock import patch
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig,TenantUser,Tenant
from apps.catalog.models import Slot,MenuSchedule,MenuItem
from apps.catalog.services import customer_slot_is_open
from apps.delivery.models import DeliveryZone
from apps.delivery.policies import (DINNER_MESSAGE,BREAKFAST_MESSAGE,BREAKFAST_DINNER_MESSAGE,SNACKS_ONLY_MESSAGE,COURIER_NOTICE)
from apps.orders.models import Order,OrderEvent,CourierCharge
from apps.orders.services import OrderError,RequestedLine,create_order,get_or_create_customer,advance_status
from apps.orders.courier import record_dispatch,confirm_courier_payment,release_courier_drafts
from apps.orders.reports import report_data,daily_sales
from apps.messaging.models import OutboundMessage
from apps.storefront.tests.test_storefront import kitchen,menu,HOST,_add
from apps.storefront.tests.test_checkout import details,review,placedata


@pytest.fixture
def meals(kitchen,menu):
    tomorrow=menu['date']+timedelta(days=1)
    with tenant_context(kitchen):
        slots={'lunch':menu['slot']}
        for key in ['breakfast','dinner','snacks']:
            slots[key]=Slot.objects.create(key=key,label=key.title(),order_cutoff=time(20))
        for slot in slots.values():
            MenuSchedule.objects.create(item=menu['item'],slot=slot,mode='date',on_date=tomorrow)
        TenantConfig.objects.filter(tenant=kitchen).update(features={'snacks_courier':True},checkout_settings={'courier_enabled':True,'courier_fee':'55','courier_minimum':'100'})
    return slots,tomorrow


def add(client,menu,key,day,qty=1):
    return _add(client,menu,delta=qty,slot_key=key,delivery_date=day.isoformat())


def test_breakfast_lunch_and_snacks_combine_same_product_separately_with_one_area_fee(client,kitchen,menu,meals):
    slots,day=meals
    for key in ['breakfast','lunch','snacks']:add(client,menu,key,day)
    page=client.get('/cart/',HTTP_HOST=HOST)
    assert page.context['cart'].count==3
    assert len(page.context['totals']['lines'])==3
    checked=review(client)
    assert checked.context['quote']['subtotal']==Decimal('360')
    assert checked.context['quote']['delivery_fee']==Decimal('20')
    assert checked.context['quote']['total']==Decimal('380')
    post=placedata(checked);response=client.post('/checkout/',post,HTTP_HOST=HOST)
    assert response.status_code==302
    assert client.post('/checkout/',post,HTTP_HOST=HOST)['Location']==response['Location']
    with tenant_context(kitchen):
        order=Order.objects.get()
        assert order.delivery_fee==Decimal('20') and order.total==Decimal('380')
        assert {line['meal_key'] for line in order.items}=={'breakfast','lunch','snacks'}
        assert order.item_count==3 and Order.objects.count()==1
        from apps.billing.services import confirm_payment,issue_bill
        profile=kitchen.billing_profile;profile.legal_name='Kitchen';profile.address='Chennai';profile.fssai_no='12345678901234';profile.state='Tamil Nadu';profile.state_code='33';profile.save()
        confirm_payment(order,actor='test:manual');bill=issue_bill(order)
        assert bill.total==Decimal('380')
        assert len([line for line in bill.lines if line['description']=='Delivery fee'])==1


@pytest.mark.parametrize('first,second',[('breakfast','dinner'),('lunch','dinner'),('snacks','dinner'),('dinner','breakfast'),('dinner','lunch'),('dinner','snacks')])
def test_dinner_rejects_every_other_meal_with_exact_message(client,kitchen,menu,meals,first,second):
    _,day=meals;add(client,menu,first,day);response=add(client,menu,second,day)
    page=client.get('/cart/',HTTP_HOST=HOST)
    assert DINNER_MESSAGE in page.content.decode()
    assert page.context['cart'].count==1


@pytest.mark.parametrize('allowed,key,message',[
    (['lunch','dinner','snacks'],'breakfast',BREAKFAST_MESSAGE),
    (['lunch','snacks'],'breakfast',BREAKFAST_DINNER_MESSAGE),
    (['lunch','snacks'],'dinner',BREAKFAST_DINNER_MESSAGE),
    (['snacks'],'breakfast',SNACKS_ONLY_MESSAGE),
    (['snacks'],'lunch',SNACKS_ONLY_MESSAGE),
    (['snacks'],'dinner',SNACKS_ONLY_MESSAGE),
])
def test_pincode_category_restrictions_return_exact_customer_messages(client,kitchen,menu,meals,allowed,key,message):
    _,day=meals
    with tenant_context(kitchen):DeliveryZone.objects.filter(pincode='641001').update(slot_keys=allowed)
    add(client,menu,key,day,2)
    page=review(client)
    assert message in page.content.decode() and 'checkout_token' not in page.context
    with tenant_context(kitchen):assert not Order.objects.exists()


def test_same_pincode_area_choice_is_required_and_controls_one_charge(client,kitchen,menu,meals):
    _,day=meals
    with tenant_context(kitchen):
        a=DeliveryZone.objects.create(pincode='600041',area_name='Thiruvanmiyur',delivery_fee=40,min_order=100,slot_keys=['lunch','snacks'])
        b=DeliveryZone.objects.create(pincode='600041',area_name='Kottivakkam',delivery_fee=60,min_order=100,slot_keys=['lunch','snacks'])
    add(client,menu,'lunch',day);add(client,menu,'snacks',day)
    response=review(client,details(pincode='600041'))
    assert 'checkout_token' not in response.context
    assert 'Thiruvanmiyur – ₹40.00' in response.content.decode() and 'Kottivakkam – ₹60.00' in response.content.decode()
    for zone,fee in [(a,40),(b,60)]:
        response=review(client,details(pincode='600041',zone_id=str(zone.pk)))
        assert response.context['quote']['delivery_fee']==Decimal(fee)
        assert response.context['quote']['total']==Decimal(240+fee)


def test_opening_window_supports_previous_day_ten_until_delivery_day_three(kitchen,menu):
    with tenant_context(kitchen):
        slot=menu['slot'];slot.order_days_before=1;slot.order_opens_at=time(10);slot.order_cutoff=time(15);slot.save()
        day=menu['date']+timedelta(days=1)
        at=lambda date_,clock:timezone.make_aware(datetime.combine(date_,clock))
        assert not customer_slot_is_open(slot,day,now=at(menu['date'],time(9,59)))
        assert customer_slot_is_open(slot,day,now=at(menu['date'],time(10)))
        assert customer_slot_is_open(slot,day,now=at(day,time(14,59)))
        assert not customer_slot_is_open(slot,day,now=at(day,time(15)))


@pytest.mark.parametrize('city,state,country,pin,phone',[
    ('Madurai','Tamil Nadu','India','625001','9876543210'),
    ('Bengaluru','Karnataka','India','560001','9876543210'),
    ('London','London','United Kingdom','SW1A 1AA','+447700900123'),
])
def test_outside_chennai_courier_excludes_fee_and_holds_both_notices(client,kitchen,menu,meals,city,state,country,pin,phone):
    with tenant_context(kitchen):item=MenuItem.objects.create(name='Snacks box',fulfilment='courier',price=200)
    client.post('/cart/add/',{'kind':'shop','item_id':item.pk},HTTP_HOST=HOST)
    data=details(city=city,state=state,country=country,pincode=pin,phone=phone)
    page=review(client,data)
    assert COURIER_NOTICE in page.content.decode()
    assert page.context['quote']['courier_deferred']
    assert page.context['quote']['delivery_fee']==0 and page.context['quote']['total']==200
    assert client.post('/checkout/',placedata(page,data),HTTP_HOST=HOST).status_code==302
    with tenant_context(kitchen):
        order=Order.objects.get();assert order.address['country']==country
        assert order.address['state_code']=={'Tamil Nadu':'33','Karnataka':'29','London':'96'}[state]
        assert CourierCharge.objects.get(order=order).amount is None
        drafts=OutboundMessage.objects.filter(dedupe_key__startswith=f'courier:{order.pk}:')
        assert drafts.count()==2 and set(drafts.values_list('status',flat=True))=={'held'}
        assert all(COURIER_NOTICE in d.payload['body'] for d in drafts)
        from apps.orders.courier import prepare_courier_charge
        prepare_courier_charge(order);assert drafts.count()==2
        with pytest.raises(OrderError):release_courier_drafts(kitchen)
        with pytest.raises(OrderError):record_dispatch(order,amount=70,courier_name='Courier',tracking_number='TRACK',actor='test')
        for status in ['confirmed','preparing','out_for_delivery']:advance_status(order,status,actor='test')
        charge=record_dispatch(order,amount='70.00',courier_name='Courier',tracking_number='TRACK',actor='test')
        assert charge.amount==70 and order.total==200
        record_dispatch(order,amount='70.00',courier_name='Courier',tracking_number='TRACK',actor='test')
        assert OutboundMessage.objects.filter(dedupe_key__startswith=f'courier:{order.pk}:').count()==4
        with pytest.raises(OrderError):record_dispatch(order,amount='71',courier_name='Courier',tracking_number='OTHER',actor='test')
        confirm_courier_payment(order,reference='cash collected',actor='test');confirm_courier_payment(order,reference='again',actor='test')
        order.refresh_from_db();assert order.total==200 and order.courier_charge.paid_at
        assert OutboundMessage.objects.filter(dedupe_key__startswith=f'courier:{order.pk}:').count()==6


def test_local_snacks_use_pincode_and_area_fee_instead_of_courier(client,kitchen,menu,meals):
    with tenant_context(kitchen):item=MenuItem.objects.create(name='Snacks',fulfilment='courier',price=200)
    client.post('/cart/add/',{'kind':'shop','item_id':item.pk},HTTP_HOST=HOST)
    page=review(client,details(city='Chennai',pincode='641001'))
    assert not page.context['quote']['courier_deferred']
    assert page.context['quote']['delivery_fee']==20 and page.context['quote']['total']==220


def test_live_reports_use_line_categories_and_exact_received_time_range(client,kitchen,menu,meals):
    _,day=meals
    for key in ['breakfast','lunch']:add(client,menu,key,day,2)
    checked=review(client);assert client.post('/checkout/',placedata(checked),HTTP_HOST=HOST).status_code==302
    now=timezone.localtime()
    with tenant_context(kitchen):
        Order.objects.update(placed_at=now)
        report=report_data(start=now-timedelta(minutes=1),end=now+timedelta(minutes=1),meal='lunch')
        assert len(report['rows'])==1 and report['rows'][0]['quantity']==2 and report['items_amount']==240
        assert report_data(start=now+timedelta(seconds=1),end=now+timedelta(minutes=1))['quantity']==0
        sales=daily_sales();assert sales['order_value']==500 and sales['order_count']==1
        assert sales['paid_order_value']==0
        from apps.billing.services import confirm_payment
        confirm_payment(Order.objects.get(),actor='test')
        OrderEvent.objects.filter(note__startswith='Payment receipt confirmed.').update(at=now)
        assert daily_sales()['manual_receipts']==500
    user=get_user_model().objects.create_user(username='report-owner');TenantUser.all_tenants.create(tenant=kitchen,user=user,role='owner');client.force_login(user)
    params={'start':(now-timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'),'end':(now+timedelta(minutes=2)).strftime('%Y-%m-%dT%H:%M'),'meal':'lunch','export':'csv'}
    response=client.get('/manage/reports/',params,HTTP_HOST=HOST)
    assert response.status_code==200 and 'attachment' in response['Content-Disposition']
    assert 'Veg Meals' in response.content.decode() and 'lunch' in response.content.decode()
    response=client.get('/manage/reports/',HTTP_HOST=HOST);assert response.status_code==200


@pytest.fixture
def dispatched_courier(client,kitchen,menu,meals):
    with tenant_context(kitchen):item=MenuItem.objects.create(name='Courier snack box',fulfilment='courier',price=200)
    client.post('/cart/add/',{'kind':'shop','item_id':item.pk},HTTP_HOST=HOST)
    data=details(city='Madurai',pincode='625001')
    page=review(client,data);client.post('/checkout/',placedata(page,data),HTTP_HOST=HOST)
    with tenant_context(kitchen):
        order=Order.objects.get()
        from apps.billing.services import confirm_payment
        confirm_payment(order,actor='test')
        for status in ['confirmed','preparing','out_for_delivery']:advance_status(order,status,actor='test')
        return record_dispatch(order,amount=70,courier_name='Courier',tracking_number='TRACK',actor='test')


def courier_connection(kitchen,mode):
    from apps.payments.models import RazorpayConnection
    config=TenantConfig.objects.get(tenant=kitchen);config.checkout_settings={**config.checkout_settings,'courier_online_enabled':True};config.save(update_fields=['checkout_settings'])
    conn=RazorpayConnection(mode=mode,key_id='rzp_'+mode+'_Courier',enabled=True)
    conn.key_secret='courier-test-secret';conn.webhook_secret='courier-test-webhook';conn.save();return conn


@pytest.mark.parametrize('mode',['test','live'])
def test_separate_courier_payment_verifies_amount_without_recharging_food(kitchen,dispatched_courier,mode):
    import hashlib,hmac
    from unittest.mock import Mock
    from apps.payments import courier
    with tenant_context(kitchen):
        conn=courier_connection(kitchen,mode)
        api=Mock();api.secret='courier-test-secret'
        api.create_order.side_effect=lambda intent:{'id':'order_Courier','receipt':intent.receipt,'amount':intent.amount,'currency':'INR'}
        with patch('apps.payments.courier.client',return_value=api):
            intent=courier.start(dispatched_courier);assert intent.amount==7000
            assert courier.start(dispatched_courier).pk==intent.pk and api.create_order.call_count==1
            entity={'id':'pay_Courier','order_id':'order_Courier','amount':7000,'currency':'INR','status':'captured','captured':True}
            api.payment.return_value=entity
            with pytest.raises(Exception):courier.verify(intent,'order_Courier','pay_Courier','wrong')
            signature=hmac.new(api.secret.encode(),b'order_Courier|pay_Courier',hashlib.sha256).hexdigest()
            courier.verify(intent,'order_Courier','pay_Courier',signature)
            courier.verify(intent,'order_Courier','pay_Courier',signature)
        dispatched_courier.refresh_from_db()
        assert bool(dispatched_courier.paid_at)==(mode=='live')
        dispatched_courier.order.refresh_from_db()
        assert dispatched_courier.order.total==200 and dispatched_courier.order.delivery_fee==0


def test_courier_capture_rejects_wrong_amount_and_webhook_retries_are_idempotent(kitchen,dispatched_courier):
    from unittest.mock import Mock
    from apps.payments import courier,services
    from apps.payments.provider import PaymentError
    with tenant_context(kitchen):
        conn=courier_connection(kitchen,'live');api=Mock()
        api.create_order.side_effect=lambda intent:{'id':'order_Courier','receipt':intent.receipt,'amount':intent.amount,'currency':'INR'}
        entity={'id':'pay_Courier','order_id':'order_Courier','amount':7000,'currency':'INR','status':'captured','captured':True}
        with patch('apps.payments.courier.client',return_value=api):
            intent=courier.start(dispatched_courier)
            with pytest.raises(PaymentError):courier.apply_capture(intent,{**entity,'amount':1})
            with pytest.raises(PaymentError):courier.apply_capture(intent,{**entity,'currency':'USD'})
            api.payment.return_value=entity
            body={'event':'payment.captured','payload':{'payment':{'entity':entity}}}
            services.ingest_event(conn,'courier-event',body);services.ingest_event(conn,'courier-event',body)
        dispatched_courier.refresh_from_db();assert dispatched_courier.paid_at
        assert OutboundMessage.objects.filter(dedupe_key__startswith=f'courier:{dispatched_courier.order_id}:paid:').count()==2


def test_uncertain_courier_setup_reconciles_without_duplicate_provider_order(kitchen,dispatched_courier):
    from unittest.mock import Mock
    from apps.payments import courier
    from apps.payments.provider import PaymentError
    with tenant_context(kitchen):
        courier_connection(kitchen,'live');api=Mock();api.create_order.side_effect=PaymentError(uncertain=True)
        with patch('apps.payments.courier.client',return_value=api):
            with pytest.raises(PaymentError):courier.start(dispatched_courier)
            api.find_order.side_effect=lambda intent:{'id':'order_Courier','receipt':intent.receipt,'amount':intent.amount,'currency':'INR'}
            assert courier.start(dispatched_courier).provider_order_id=='order_Courier'
            assert api.create_order.call_count==1 and api.find_order.call_count==1


def test_offline_courier_payment_stays_manual_and_private(client,kitchen,dispatched_courier):
    from apps.payments import courier
    from apps.payments.provider import PaymentError
    from django.test import Client
    with tenant_context(kitchen):
        with pytest.raises(PaymentError):courier.start(dispatched_courier)
        reference=dispatched_courier.order.external_ref.split(':')[-1]
    response=Client().post(f'/checkout/complete/{reference}/courier/pay/',HTTP_HOST=HOST)
    assert response.status_code==404


def test_held_courier_messages_use_approved_templates_when_released(kitchen,dispatched_courier):
    with tenant_context(kitchen):
        config=kitchen.config;config.checkout_settings={**config.checkout_settings,'courier_notifications_enabled':True,'courier_customer_template':'courier_customer_update','courier_team_template':'courier_team_update','courier_template_language':'en'};config.save()
        count=release_courier_drafts(kitchen)
        assert count==4
        rows=OutboundMessage.objects.filter(dedupe_key__startswith=f'courier:{dispatched_courier.order_id}:')
        assert set(rows.values_list('status',flat=True))=={'pending'}
        assert all(r.payload['kind']=='template' and len(r.payload['params'])==2 for r in rows)


def test_reports_are_private_and_cannot_cross_stores(client,kitchen,menu):
    from apps.tenancy.models import TenantDomain,TenantStatus
    assert client.get('/manage/reports/',HTTP_HOST=HOST).status_code==302
    user=get_user_model().objects.create_user(username='report-restricted');TenantUser.all_tenants.create(tenant=kitchen,user=user,role='owner');client.force_login(user)
    other=Tenant.objects.create(slug='other',name='Other',status=TenantStatus.ACTIVE);TenantDomain.objects.create(tenant=other,hostname='other.localhost',is_primary=True)
    assert client.get('/manage/reports/',HTTP_HOST='other.localhost').status_code==403


def test_staff_combined_categories_have_one_fee_and_reportable_snapshots(kitchen,menu,meals):
    from apps.billing.services import create_staff_order
    slots,day=meals
    with tenant_context(kitchen):
        zone=DeliveryZone.objects.get(pincode='641001')
        order=create_staff_order(kitchen,name='Buyer',phone='919999999999',channel='manual',payment_mode='manual',
            requested=[(menu['item'].pk,1,'breakfast'),(menu['item'].pk,1,'lunch')],token='staff-combined',actor='test',zone=zone,address='Local street',delivery_date=day)
        assert order.total==260 and order.delivery_fee==20
        assert {line['meal_key'] for line in order.items}=={'breakfast','lunch'}
        with pytest.raises(ValueError,match='Dinner cannot be combined'):
            create_staff_order(kitchen,name='Buyer',phone='919999999999',channel='manual',payment_mode='manual',
                requested=[(menu['item'].pk,1,'dinner'),(menu['item'].pk,1,'lunch')],token='staff-dinner-combined',actor='test',zone=zone,address='Local street')


def test_staff_cannot_relabel_packed_snacks_as_breakfast(kitchen,menu,meals):
    from apps.billing.services import create_staff_order
    with tenant_context(kitchen):
        item=MenuItem.objects.create(name='Packed snack',fulfilment='courier',price=200)
        with pytest.raises(ValueError,match='must use the Snacks'):
            create_staff_order(kitchen,name='Buyer',phone='919999999999',channel='manual',payment_mode='manual',requested=[(item.pk,1,'breakfast')],token='wrong-category',actor='test')
