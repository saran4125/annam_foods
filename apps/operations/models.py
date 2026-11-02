from django.db import models
from apps.tenancy.managers import TenantOwnedModel


class RateLimitBucket(TenantOwnedModel):
    key = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveIntegerField(default=0)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=['tenant','key','window_start'],name='unique_rate_limit_window')]


class WorkerPulse(TenantOwnedModel):
    name = models.CharField(max_length=40)
    updated_at = models.DateTimeField()

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=['tenant','name'],name='unique_worker_pulse')]
