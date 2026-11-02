from django.conf import settings
from django.utils import timezone
from apps.jobs.services import run_daily_handoff,send_due_messages
from .models import RateLimitBucket


def scheduled_maintenance():
    run_daily_handoff()
    RateLimitBucket.all_tenants.filter(expires_at__lt=timezone.now()).delete()
    # Provider delivery stays offline until an operator deliberately enables it.
    if getattr(settings,'ENABLE_TRANSACTIONAL_MESSAGES',False):send_due_messages()
