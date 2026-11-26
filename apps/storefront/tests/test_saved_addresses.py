import uuid
from django.test import RequestFactory
from apps.owner.tests.test_owner import kitchens, owner, signed_in, catalog, HOST
from apps.orders.models import Customer,Order
from apps.storefront.checkout import saved_address
from apps.tenancy.context import tenant_context


def test_address_lookup_is_scoped_to_signed_browser_tenant_and_pincode(signed_in,kitchens):
    key=uuid.uuid4().hex
    with tenant_context(kitchens[0]):
        customer=Customer.objects.create(name='Browser buyer',phone='919876543210')
        Order.objects.create(order_no='ADDRESS-1',customer=customer,channel='web',payment_mode='manual',external_ref=f'web:{key}:{uuid.uuid4().hex}',address={'recipient_name':'Browser buyer','line1':'12 Test lane','pincode':'600005','country':'India','phone':'919876543210'},items=[],subtotal=100,total=100)
    session=signed_in.session;session['checkout.browser.'+str(kitchens[0].pk)]=key;session.save()
    response=signed_in.get('/checkout/address/',{'pincode':'600005'},HTTP_HOST=HOST)
    assert response.json()['address']['line1']=='12 Test lane' and 'no-store' in response['Cache-Control']
    assert signed_in.get('/checkout/address/',{'pincode':'600006'},HTTP_HOST=HOST).json()['address'] is None
    request=RequestFactory().get('/');request.session={'checkout.browser.'+str(kitchens[1].pk):key};request.tenant=kitchens[1]
    with tenant_context(kitchens[1]):assert saved_address(request,'600005') is None
    from django.test import Client
    assert Client().get('/checkout/address/',{'pincode':'600005'},HTTP_HOST=HOST).json()['address'] is None
