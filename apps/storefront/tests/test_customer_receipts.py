"""Customer documents remain browser-bound and preserve financial snapshots."""
from io import BytesIO
import pytest
from django.test import Client
from apps.tenancy.context import tenant_context
from apps.orders.models import Order
from apps.billing.models import Invoice, InvoiceSequence
from apps.billing.services import issue_bill
from .test_storefront import HOST, kitchen, menu
from .test_checkout import prepare, review, placedata

pytestmark = pytest.mark.django_db


def place(client, menu):
    prepare(client, menu)
    return client.post('/checkout/', placedata(review(client)), HTTP_HOST=HOST)['Location']


def test_paid_manual_customer_gets_snapshot_pdf_and_browser_bound_refresh(client, kitchen, menu):
    url = place(client, menu)
    assert client.get(url+'bill/download/', HTTP_HOST=HOST).status_code == 404
    assert client.get(url+'status/', HTTP_HOST=HOST).json()['download_url'] == ''
    with tenant_context(kitchen):
        order = Order.objects.get()
        order.payment_status = 'paid'
        order.save(update_fields=['payment_status'])
        # Paid without an issued invoice stays paid and exposes no invented document.
    assert client.get(url+'status/', HTTP_HOST=HOST).json()['paid']
    assert client.get(url+'status/', HTTP_HOST=HOST).json()['download_url'] == ''
    with tenant_context(kitchen):
        profile = kitchen.billing_profile
        profile.address = 'Seller street'
        profile.state = 'Tamil Nadu'
        profile.state_code = '33'
        profile.fssai_no = '12345678901234'
        profile.save()
        invoice = issue_bill(order)
    page = client.get(url, HTTP_HOST=HOST)
    assert b'Download invoice PDF' in page.content
    state = client.get(url+'status/', HTTP_HOST=HOST).json()
    pdf = client.get(state['download_url'], HTTP_HOST=HOST)
    assert pdf['Content-Type'] == 'application/pdf' and pdf.content.startswith(b'%PDF-')
    from pypdf import PdfReader
    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert invoice.number in text and 'Customer One' in text and '260.00' in text
    assert Client().get(state['download_url'], HTTP_HOST=HOST).status_code == 404
    assert Client().get(url+'status/', HTTP_HOST=HOST).status_code == 404
    assert b'View your recent order' in client.get('/cart/', HTTP_HOST=HOST).content
    assert b'View your recent order' not in Client().get('/cart/', HTTP_HOST=HOST).content
    assert client.get(state['download_url'], HTTP_HOST='unknown.localhost').status_code == 404
    with tenant_context(kitchen):
        assert Invoice.objects.count() == 1


def test_pending_customer_never_gets_invoice_or_payment_flags_from_client(client, kitchen, menu):
    url = place(client, menu)
    state = client.get(url+'status/?paid=true', HTTP_HOST=HOST).json()
    assert not state['paid'] and not state['download_url']
    with tenant_context(kitchen):
        assert not Invoice.objects.exists() and not InvoiceSequence.objects.exists()


from apps.payments.tests.test_razorpay import online, api, ready, entity
from apps.payments import services as payment_services


def test_verified_test_capture_downloads_marked_receipt_without_financial_sequence(client, online, api):
    ready(online)
    before = InvoiceSequence.objects.count()
    assert client.get(online.receipt_url+'bill/download/', HTTP_HOST=HOST).status_code == 404
    payment_services.apply_payment(online.intent, entity(online))
    state = client.get(online.receipt_url+'status/', HTTP_HOST=HOST).json()
    assert state['test'] and state['download_url'] and not state['invoice_url']
    from pypdf import PdfReader
    pdf = client.get(state['download_url'], HTTP_HOST=HOST)
    text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
    assert 'SIMULATED PAYMENT' in text and 'NOT AN INVOICE' in text
    assert InvoiceSequence.objects.count() == before and not Invoice.objects.exists()



def test_guest_recent_order_survives_loss_of_session_but_not_a_different_browser(client, kitchen, menu):
    url = place(client, menu)
    cookie_name = 'guest_order_' + str(kitchen.pk)
    assert int(client.cookies[cookie_name]['max-age']) == 30 * 86400
    assert client.cookies[cookie_name]['httponly']
    returning = Client()
    returning.cookies[cookie_name] = client.cookies[cookie_name].value
    cart = returning.get('/cart/', HTTP_HOST=HOST)
    assert b'View your recent order' in cart.content
    assert b'Veg Meals' in cart.content and b'260' in cart.content
    assert returning.get(url, HTTP_HOST=HOST).status_code == 200
    stranger = Client()
    stranger.cookies[cookie_name] = client.cookies[cookie_name].value + 'tampered'
    assert b'View your recent order' not in stranger.get('/cart/', HTTP_HOST=HOST).content
    assert stranger.get(url, HTTP_HOST=HOST).status_code == 404


def test_pending_order_summary_is_private_and_allocates_no_invoice(client,kitchen,menu):
    url=place(client,menu)
    before=InvoiceSequence.all_tenants.filter(tenant=kitchen).count()
    page=client.get(url+'summary/',HTTP_HOST=HOST)
    pdf=client.get(url+'summary/download/',HTTP_HOST=HOST)
    assert page.status_code==200 and b'not a tax invoice' in page.content
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    assert Client().get(url+'summary/',HTTP_HOST=HOST).status_code==404
    with tenant_context(kitchen):
        assert not Invoice.objects.exists() and InvoiceSequence.objects.count()==before
        assert Order.objects.get().payment_status=='pending'


def test_issued_unpaid_cod_invoice_is_downloadable_without_confirming_payment(client,kitchen,menu):
    url=place(client,menu)
    with tenant_context(kitchen):
        order=Order.objects.get();order.payment_mode='cod';order.payment_status='cod_pending';order.save(update_fields=['payment_mode','payment_status'])
        profile=kitchen.billing_profile;profile.address='Seller street';profile.state='Tamil Nadu';profile.state_code='33';profile.fssai_no='12345678901234';profile.save()
        invoice=issue_bill(order,allow_unpaid=True)
    state=client.get(url+'status/',HTTP_HOST=HOST).json()
    assert not state['paid'] and state['invoice_url'] and state['download_url']
    assert client.get(state['download_url'],HTTP_HOST=HOST).content.startswith(b'%PDF-')
    with tenant_context(kitchen):
        order.refresh_from_db();assert order.payment_status=='cod_pending' and Invoice.objects.count()==1
