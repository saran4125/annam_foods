from datetime import date
from decimal import Decimal

import pytest
from django.db import transaction

from apps.billing.models import Invoice, InvoiceKind, InvoiceSequence
from apps.billing.services import (
    allocate_number, financial_year, issue_bill, issue_credit_note, request_bill, fulfil_request,
)
from apps.orders.models import Channel, Customer, Order, OrderSource, PaymentMode, PaymentStatus
from apps.tenancy.context import tenant_context
from apps.tenancy.models import BillingProfile, Tenant


@pytest.fixture
def billing_order(db):
    tenant = Tenant.objects.create(slug="billing-kitchen", name="Billing Kitchen")
    with tenant_context(tenant):
        profile = BillingProfile.objects.get(tenant=tenant)
        profile.address = "Test address"
        profile.state = "Tamil Nadu"
        profile.state_code = "33"
        profile.fssai_no = "12345678901234"
        profile.save()
        customer = Customer.objects.create(phone="919999999999", name="Buyer")
        order = Order.objects.create(
            order_no="BILLING-20261006-1234", customer=customer,
            channel=Channel.MANUAL, source=OrderSource.OWNER, payment_mode=PaymentMode.MANUAL,
            payment_status=PaymentStatus.PAID,
            items=[{"item_id": 7654321, "name": "Meal", "unit_price": "105.00", "quantity": 1, "line_total": "105.00"}],
            address={"pincode": "641001", "state_code": "33"},
            subtotal=Decimal("105"), total=Decimal("105"),
        )
    return tenant, order


@pytest.mark.django_db
def test_financial_year_changes_on_april_first():
    assert financial_year(date(2026, 3, 31)) == "25-26"
    assert financial_year(date(2026, 4, 1)) == "26-27"


@pytest.mark.django_db
def test_number_allocation_increments_inside_the_callers_transaction(billing_order):
    tenant, _ = billing_order
    with tenant_context(tenant):
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                fy, seq, number = allocate_number(tenant)
                assert seq == 1 and number == f"AF/{fy}/00001"
                raise RuntimeError("rollback")
        fy, seq, number = allocate_number(tenant)
        assert seq == 1 and number == f"AF/{fy}/00001"


@pytest.mark.django_db
def test_issue_bill_snapshots_seller_buyer_and_reuses_existing_number(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        invoice = issue_bill(order)
        assert invoice.kind == InvoiceKind.BILL
        assert invoice.number.endswith("00001")
        assert invoice.seller["fssai_no"] == "12345678901234"
        assert invoice.buyer["phone"] == order.customer.phone
        assert invoice.total == Decimal("105.00")
        assert issue_bill(order).pk == invoice.pk
        assert Invoice.objects.filter(order=order).count() == 1
        with pytest.raises(Exception, match="immutable"):
            invoice.total = Decimal("1.00")
            invoice.save()


@pytest.mark.django_db
def test_unpaid_order_cannot_be_billed_and_does_not_consume_a_number(billing_order):
    tenant, order = billing_order
    order.payment_status = PaymentStatus.PENDING
    order.save()
    with tenant_context(tenant), pytest.raises(ValueError, match="Payment must be confirmed"):
        issue_bill(order)
    with tenant_context(tenant):
        assert not InvoiceSequence.objects.exists()


@pytest.mark.django_db
def test_credit_note_is_a_separate_series_and_keeps_the_original_unchanged(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        invoice = issue_bill(order)
        note = issue_credit_note(invoice, Decimal("25.00"), reason="Partial refund")
        assert note.original_id == invoice.pk
        assert note.order_id == invoice.order_id
        assert note.total == Decimal("25.00")
        assert note.number.startswith("AFC/")
        assert invoice.total == Decimal("105.00")
        assert issue_credit_note(invoice, Decimal("25.00")).number.endswith("00002")


@pytest.mark.django_db
def test_bill_request_can_be_fulfilled_and_rate_limit_is_per_phone(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        request = request_bill(phone=order.customer.phone, customer=order.customer, order=order)
        invoice = fulfil_request(request, order)
        request.refresh_from_db()
        assert request.status == "fulfilled"
        assert request.invoice_id == invoice.pk
        assert fulfil_request(request, order).pk == invoice.pk


@pytest.mark.django_db
def test_bill_requests_enforce_the_profile_daily_limit(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        for _ in range(5):
            request_bill(phone=order.customer.phone, customer=order.customer)
        with pytest.raises(ValueError, match="daily bill request limit"):
            request_bill(phone=order.customer.phone, customer=order.customer)


@pytest.mark.django_db
def test_delivered_cod_still_requires_confirmed_payment_even_with_force(billing_order):
    tenant, order = billing_order
    order.payment_status = PaymentStatus.COD_PENDING
    order.status = "delivered"
    order.save()
    with tenant_context(tenant), pytest.raises(ValueError, match="Payment must be confirmed"):
        issue_bill(order, force=True)


@pytest.mark.django_db
def test_discount_is_included_and_paid_total_must_match(billing_order):
    tenant, order = billing_order
    order.discount = Decimal("5")
    order.total = Decimal("100")
    order.save()
    with tenant_context(tenant):
        invoice = issue_bill(order)
        assert invoice.total == Decimal("100")
        assert invoice.lines[0]["discount"] == "5.00"


@pytest.mark.django_db
def test_wrong_paid_total_does_not_allocate_a_number(billing_order):
    tenant, order = billing_order
    order.total = Decimal("999")
    order.save()
    with tenant_context(tenant):
        with pytest.raises(ValueError, match="does not match"):
            issue_bill(order)
        assert not InvoiceSequence.objects.exists()


@pytest.mark.django_db
def test_registered_bill_splits_inclusive_gst_and_retains_seller_snapshot(billing_order):
    tenant, order = billing_order
    with tenant_context(tenant):
        profile = BillingProfile.objects.get(tenant=tenant)
        profile.gst_mode = "regular"
        profile.gstin = "33ABCDE1234F1Z5"
        profile.save()
        invoice = issue_bill(order)
        assert invoice.taxable == Decimal("100")
        assert invoice.cgst == Decimal("2.50")
        assert invoice.sgst == Decimal("2.50")
        assert invoice.total == order.total


@pytest.mark.django_db(transaction=True)
def test_simultaneous_bill_requests_issue_one_bill_and_one_number():
    from concurrent.futures import ThreadPoolExecutor
    from django.db import connections
    tenant = Tenant.objects.create(slug="concurrent-bills", name="Concurrency Kitchen")
    with tenant_context(tenant):
        profile = tenant.billing_profile
        profile.address = "Test address"
        profile.state = "Tamil Nadu"
        profile.state_code = "33"
        profile.fssai_no = "12345678901234"
        profile.save()
        customer = Customer.objects.create(phone="919000000000")
        order = Order.objects.create(order_no="CONCURRENT-1", customer=customer, channel="manual",
            payment_status="paid", subtotal="100", total="100",
            items=[{"name": "Lunch", "quantity": 1, "unit_price": "100", "line_total": "100"}])
    def attempt(_):
        try:
            return issue_bill(order).pk
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(attempt, range(2)))
    assert ids[0] == ids[1]
    with tenant_context(tenant):
        assert Invoice.objects.count() == 1
        assert InvoiceSequence.objects.get().next_no == 2
