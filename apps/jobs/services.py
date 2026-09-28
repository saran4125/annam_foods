"""Scheduled work uses each kitchen's scope and wall clock."""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from apps.tenancy.context import all_tenants, tenant_context
from apps.tenancy.models import Tenant
from .models import DailyKitchenRun


def due_local_kitchens(at: datetime):
    """Return tenants whose local clock has crossed 04:00, once per date.

    A delayed scheduler still catches the run later that same day. The unique
    row makes repeat delivery safe when multiple workers wake together.
    """
    with all_tenants():
        tenants = list(Tenant.objects.select_related("config").all())
    for tenant in tenants:
        local = at.astimezone(ZoneInfo(tenant.config.timezone))
        if local.hour < 4:
            continue
        with tenant_context(tenant), timezone.override(tenant.config.timezone):
            _, created = DailyKitchenRun.objects.get_or_create(local_date=local.date())
            if created:
                yield tenant, local.date()


def run_daily_handoff(at=None):
    """Record each kitchen's local business-day transition for downstream jobs."""
    return [(tenant.id, day.isoformat()) for tenant, day in due_local_kitchens(at or timezone.now())]


def send_due_messages():
    from apps.messaging.services import dispatch_pending
    with all_tenants():
        tenants = list(Tenant.objects.select_related("config").all())
    for tenant in tenants:
        with tenant_context(tenant), timezone.override(tenant.config.timezone):
            dispatch_pending(tenant=tenant)
