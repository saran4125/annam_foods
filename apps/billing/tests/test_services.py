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
    with tenant_context(tenant), pytest.raises(ValueError, match="paid or delivered COD"):
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
