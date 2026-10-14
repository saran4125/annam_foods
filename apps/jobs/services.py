"""Scheduled work uses each kitchen's scope and wall clock."""
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from django.utils import timezone
from apps.tenancy.context import all_tenants, tenant_context
from apps.tenancy.models import Tenant, TenantConfig, TenantStatus
from .models import DailyKitchenRun

log = logging.getLogger(__name__)


def _config_for(tenant):
    """Repair a missing optional one-to-one config without stopping a sweep."""
    config = TenantConfig.objects.filter(tenant=tenant).first()
    return config or TenantConfig.objects.create(tenant=tenant)


def due_local_kitchens(at: datetime):
    """Return tenants whose local clock has crossed 04:00, once per date.

    A delayed scheduler still catches the run later that same day. The unique
    row makes repeat delivery safe when multiple workers wake together.
    """
    with all_tenants():
        tenants = list(Tenant.objects.all())
    for tenant in tenants:
        try:
            config = _config_for(tenant)
            local = at.astimezone(ZoneInfo(config.timezone))
            if local.hour < 4:
                continue
            with tenant_context(tenant), timezone.override(config.timezone):
                _, created = DailyKitchenRun.objects.get_or_create(local_date=local.date())
                if created:
                    yield tenant, local.date()
        except Exception:
            log.exception("daily kitchen handoff failed for tenant %s", tenant.slug)


def run_daily_handoff(at=None):
    """Record each kitchen's local business-day transition for downstream jobs."""
    return [(tenant.id, day.isoformat()) for tenant, day in due_local_kitchens(at or timezone.now())]


def send_due_messages():
    from apps.messaging.services import dispatch_pending
    with all_tenants():
        tenants = list(Tenant.objects.all())
    for tenant in tenants:
        if tenant.status in {TenantStatus.SUSPENDED, TenantStatus.CANCELLED}:
            continue
        try:
            config = _config_for(tenant)
            with tenant_context(tenant), timezone.override(config.timezone):
                dispatch_pending(tenant=tenant)
        except Exception:
            log.exception("message dispatch failed for tenant %s", tenant.slug)
