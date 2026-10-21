"""A bounded scheduler command; provider reads only, never requests refunds or new charges."""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from apps.tenancy.context import all_tenants, tenant_context
from apps.payments.models import PaymentIntent, Refund
from apps.payments.provider import PaymentError
from apps.payments.services import reconcile_payment, refresh_refund


class Command(BaseCommand):
    help = 'Reconcile pending Razorpay payments/refunds. Safe to schedule every 15 minutes.'

    def handle(self, *args, **options):
        with all_tenants():
            intents = list(PaymentIntent.objects.filter(
                Q(created_at__gte=timezone.now() - timedelta(days=2), order__payment_status__in=['pending', 'failed']) |
                ~Q(bill_error='') | Q(state='refund_pending')).exclude(state__in=['new', 'error', 'refunded'])
                .select_related('tenant', 'order').order_by('updated_at')[:100])
            refunds = list(Refund.objects.exclude(state__in=['processed', 'failed'])
                .select_related('tenant', 'intent').order_by('updated_at')[:100])
        checked = failed = 0
        for intent in intents:
            with tenant_context(intent.tenant):
                try:
                    reconcile_payment(intent)
                    checked += 1
                except PaymentError:
                    failed += 1
        for refund in refunds:
            with tenant_context(refund.tenant):
                try:
                    refresh_refund(refund)
                    checked += 1
                except PaymentError:
                    failed += 1
        self.stdout.write(f'Checked {checked} payment/refund records; {failed} require another check.')
