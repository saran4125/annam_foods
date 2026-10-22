from decimal import Decimal

import pytest
from django.template.loader import render_to_string

from apps.billing.presentation import logo_url, receipt_details
from apps.billing.services import issue_bill, issue_credit_note
from apps.billing.tests.test_services import billing_order
from apps.tenancy.context import tenant_context
from apps.tenancy.models import BillingProfile


@pytest.mark.django_db
def test_receipt_uses_issued_logo_and_seller_after_branding_changes(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        config = tenant.config
        config.theme = {'logo_url': '/media/brand/original.png'}
        config.tagline = 'Our original store tagline'
        config.save()
        invoice = issue_bill(order)
        config.theme = {'logo_url': '/media/brand/replacement.png'}
        config.tagline = 'Replacement tagline'
        config.save()
        profile = BillingProfile.objects.get(tenant=tenant)
        profile.legal_name = 'Changed legal identity'
        profile.save()
        invoice.refresh_from_db()
        receipt = receipt_details(invoice)
        html = render_to_string('billing/_invoice_body.html', {'invoice': invoice})
    assert receipt['logo_url'] == '/media/brand/original.png'
    assert receipt['tagline'] == 'Our original store tagline'
    assert 'Our original store tagline' in html and 'Replacement tagline' not in html
    assert invoice.seller['logo_url'] == '/media/brand/original.png'
    assert 'Changed legal identity' not in html
    assert 'Payment received' in html and invoice.number in html
    assert 'Total paid' in html and '₹105.00' in html
    assert 'DEMO' not in html and 'SAMPLE' not in html


@pytest.mark.django_db
def test_receipt_formats_delivery_fields_without_repeating_customer_or_internal_codes(billing_order):
    tenant, order = billing_order
    order.address = {'recipient_name': 'Actual Buyer', 'phone': '919888888888',
                     'line1': '<script>bad()</script>', 'line2': 'Triplicane', 'area': 'Triplicane',
                     'city': 'Chennai', 'state': 'Tamil Nadu', 'state_code': '33',
                     'pincode': '600005', 'email': 'private@example.test'}
    order.save()
    with tenant_context(tenant):
        invoice = issue_bill(order)
        data = receipt_details(invoice)
        html = render_to_string('billing/_invoice_body.html', {'invoice': invoice})
    assert data['address_lines'] == ['<script>bad()</script>', 'Triplicane', 'Chennai, Tamil Nadu, 600005']
    assert html.count('Actual Buyer') == 1
    assert html.count('919888888888') == 1
    assert 'private@example.test' not in html
    assert '<script>bad()</script>' not in html
    assert '&lt;script&gt;' in html


@pytest.mark.django_db
def test_tax_receipt_shows_snapshot_tax_breakdown_and_amounts(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        profile = BillingProfile.objects.get(tenant=tenant)
        profile.gst_mode = 'regular'
        profile.gstin = '33ABCDE1234F1Z5'
        profile.save()
        invoice = issue_bill(order)
        data = receipt_details(invoice)
        html = render_to_string('billing/_invoice_body.html', {'invoice': invoice})
    assert invoice.taxable == Decimal('100.00')
    assert sum(line['amount'] for line in data['lines']) == invoice.total
    assert 'Tax invoice' in html and 'GSTIN: 33ABCDE1234F1Z5' in html
    assert 'CGST' in html and 'SGST' in html and 'IGST' in html
    assert '₹2.50' in html and 'GST 5.00%' in html


@pytest.mark.django_db
def test_partial_credit_receipt_is_a_credit_document_and_not_payment_received(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        invoice = issue_bill(order)
        credit = issue_credit_note(invoice, Decimal('25.00'), reason='Returned item')
        html = render_to_string('billing/_invoice_body.html', {'invoice': credit})
        data = receipt_details(credit)
    assert data['is_credit'] and sum(line['amount'] for line in data['lines']) == credit.total
    assert 'Credit total' in html and '₹25.00' in html
    assert 'Original order:' in html and invoice.number in html
    assert 'Returned item' in html and 'Payment received' not in html and 'Total paid' not in html


@pytest.mark.parametrize('value', ['javascript:alert(1)', '//evil.test/logo.png', 'data:image/png;base64,abc',
                                  'https://[broken', '/\\evil.test/logo', 'https://user:password@host/logo.png'])
def test_receipt_logo_rejects_unsafe_or_malformed_urls(value):
    assert logo_url(value) == ''


def test_receipt_logo_supports_old_root_relative_uploads():
    assert logo_url('media/brand/logo.png') == '/media/brand/logo.png'


@pytest.mark.django_db
def test_older_invoice_gets_its_own_store_logo_without_rewriting_snapshot(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        invoice = issue_bill(order)
        old_seller = {key: value for key, value in invoice.seller.items() if key != 'logo_url'}
        invoice.seller = old_seller
        config = invoice.tenant.config
        config.theme = {'logo_url': '/media/brand/existing.png'}
        config.save()
        assert receipt_details(invoice)['logo_url'] == '/media/brand/existing.png'
        assert invoice.seller == old_seller


@pytest.mark.django_db
def test_collection_receipt_does_not_print_empty_delivery_section(billing_order):
    tenant, order = billing_order
    order.address = {'fulfilment': 'Collection', 'line1': ''}
    order.save()
    with tenant_context(tenant):
        invoice = issue_bill(order)
        html = render_to_string('billing/_invoice_body.html', {'invoice': invoice})
    assert 'Collection' in html and 'Delivery address' not in html


@pytest.mark.django_db
def test_dedicated_bill_logo_is_snapshotted_without_changing_the_website_logo(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        config = tenant.config
        config.theme = {'logo_url': '/media/website-original.png',
                        'billing_logo_url': '/static/branding/annam-bill-logo.png'}
        config.save()
        invoice = issue_bill(order)
        html = render_to_string('billing/_invoice_body.html', {'invoice': invoice})
    assert invoice.seller['logo_url'] == '/static/branding/annam-bill-logo.png'
    assert 'src="/static/branding/annam-bill-logo.png"' in html
    config.refresh_from_db()
    assert config.theme['logo_url'] == '/media/website-original.png'
