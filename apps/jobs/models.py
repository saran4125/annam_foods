from django.db import models
from apps.tenancy.managers import TenantOwnedModel


class DailyKitchenRun(TenantOwnedModel):
    """One 04:00 local-day handoff, durable across scheduler restarts."""
    local_date = models.DateField()
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "local_date"], name="uniq_kitchen_daily_run")]
