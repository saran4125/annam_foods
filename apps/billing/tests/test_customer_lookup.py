"""Phone-first billing recalls editable customer details without exposing other kitchens."""
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST, OTHER
from apps.billing.tests.test_portal import item, booking
from apps.orders.models import Customer, Order, Address
from apps.delivery.models import DeliveryZone
from apps.tenancy.context import tenant_context
from apps.billing.services import lookup_staff_customer

URL='/billing/customer-lookup/'


def saved_order(customer, **kwargs):
    return Order.objects.create(customer=customer,order_no=kwargs.pop('order_no','LOOKUP-1'),channel='manual',
        subtotal=Decimal('100'),total=Decimal('100'),**kwargs)


def test_lookup_requires_kitchen_staff_and_never_caches_addresses(client,kitchens,owner):
    assert client.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).status_code==302
    user=get_user_model().objects.create_user('lookup-customer',password='tests-only')
    client.force_login(user)
    assert client.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).status_code==403
    client.force_login(owner)
    assert client.get(URL,{'phone':'9999999999'},HTTP_HOST=OTHER).status_code==403
    response=client.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST)
    assert response.json()=={'found':False}
    assert 'no-store' in response['Cache-Control']


@pytest.mark.parametrize('phone',['9999999999','+91 99999-99999','919999999999'])
def test_phone_variants_recall_latest_delivery_and_exact_area(signed_in,kitchens,phone):
    with tenant_context(kitchens[0]):
        customer=Customer.objects.create(phone='919999999999',name='Saran')
        zone=DeliveryZone.objects.create(pincode='600041',area_name='Thiruvanmiyur',delivery_fee=40)
        DeliveryZone.objects.create(pincode='600041',area_name='Kottivakkam',delivery_fee=60)
        saved_order(customer,address={'line1':'Old street','pincode':'600041','area':'Kottivakkam'})
        saved_order(customer,order_no='LOOKUP-2',address={'line1':'12 New street','line2':'First floor','landmark':'Near park',
            'pincode':'600041','area':'Thiruvanmiyur','recipient_name':'Saran updated'})
        saved_order(customer,order_no='LOOKUP-3',address={'line1':'','fulfilment':'Collection','recipient_name':'Saran updated'})
    response=signed_in.get(URL,{'phone':phone},HTTP_HOST=HOST)
    data=response.json();assert data['found']
    assert data['details']['name']=='Saran updated'
    assert data['details']['address']=='12 New street\nFirst floor\nNear park'
    assert data['details']['zone']==str(zone.pk)
    assert not data['needs_area_selection']


def test_ambiguous_or_inactive_area_is_not_guessed(signed_in,kitchens):
    with tenant_context(kitchens[0]):
        customer=Customer.objects.create(phone='9999999999',name='Saran')
        DeliveryZone.objects.create(pincode='600041',area_name='Thiruvanmiyur',delivery_fee=40)
        DeliveryZone.objects.create(pincode='600041',area_name='Kottivakkam',delivery_fee=60)
        saved_order(customer,address={'line1':'Street','pincode':'600041'})
    data=signed_in.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).json()
    assert data['details']['zone']=='' and data['needs_area_selection']


def test_courier_details_and_saved_address_without_order_are_supported(signed_in,kitchens):
    with tenant_context(kitchens[0]):
        customer=Customer.objects.create(phone='9999999999',name='Saran')
        Address.objects.create(customer=customer,line1='Saved street',pincode='641001',is_default=True)
    data=signed_in.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).json()
    assert data['details']['address']=='Saved street'
    with tenant_context(kitchens[0]):
        saved_order(customer,address={'line1':'Courier street','city':'Coimbatore','state':'Tamil Nadu',
            'country':'India','pincode':'641001','courier_deferred':True})
    data=signed_in.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).json()
    assert data['details']['city']=='Coimbatore'
    assert data['details']['fulfilment_method']=='courier' and not data['needs_area_selection']


def test_lookup_does_not_cross_tenants_or_suffix_match(signed_in,kitchens):
    with tenant_context(kitchens[1]):
        customer=Customer.objects.create(phone='919999999999',name='Private rival')
        saved_order(customer,address={'line1':'Private rival address','pincode':'600005'})
    assert signed_in.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).json()=={'found':False}
    with tenant_context(kitchens[0]):
        Customer.objects.create(phone='449999999999',name='Foreign number')
    assert signed_in.get(URL,{'phone':'9999999999'},HTTP_HOST=HOST).json()=={'found':False}
    assert signed_in.get(URL,{'phone':'123'},HTTP_HOST=HOST).status_code==400
    assert signed_in.post(URL,{'phone':'9999999999'},HTTP_HOST=HOST).status_code==405


def test_filled_details_can_be_edited_and_saved_without_changing_previous_orders(signed_in,kitchens,item):
    with tenant_context(kitchens[0]):
        customer=Customer.objects.create(phone='919999999999',name='Old name')
        old=saved_order(customer,address={'line1':'Old street','recipient_name':'Old name','fulfilment':'Collection'})
    data=booking(kitchens[0],item);data.update(name='New name',address='New street')
    response=signed_in.post('/billing/new/',data,HTTP_HOST=HOST)
    assert response.status_code==302
    with tenant_context(kitchens[0]):
        new=Order.objects.exclude(pk=old.pk).get()
        assert new.address['recipient_name']=='New name' and new.address['line1']=='New street'
        old.refresh_from_db();assert old.address['line1']=='Old street' and old.address['recipient_name']=='Old name'
        assert lookup_staff_customer('9999999999')['details']['name']=='New name'
        assert lookup_staff_customer('9999999999')['details']['address']=='New street'
    page=signed_in.get('/billing/new/',HTTP_HOST=HOST).content.decode()
    assert page.index('id="id_phone"')<page.index('id="id_name"')
