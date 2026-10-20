"""Database-backed inbox worker: no Redis dependency for the Render web service."""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from apps.tenancy.context import all_tenants, tenant_context
from .models import WhatsAppForwardEvent, OutboundMessage
from .senders.inbox_io import forward_to_n8n
from .services import deliver


def process_inbox_work(limit=20):
    now = timezone.now()
    with all_tenants():
        WhatsAppForwardEvent.objects.filter(status="sending", claimed_at__lt=now-timedelta(minutes=5)).update(status="pending", claimed_at=None)
        event_ids = list(WhatsAppForwardEvent.objects.filter(status="pending", next_attempt_at__lte=now).order_by("created_at").values_list("pk", flat=True)[:limit])
    for pk in event_ids:
        with all_tenants(), transaction.atomic():
            event = WhatsAppForwardEvent.objects.select_for_update().select_related("tenant").get(pk=pk)
            if event.status != "pending":
                continue
            event.status = "sending"
            event.claimed_at = now
            event.attempts += 1
            event.save(update_fields=["status", "claimed_at", "attempts"])
        result = forward_to_n8n(event)
        with tenant_context(event.tenant):
            event.status = "sent" if result.ok else "pending" if result.retryable and event.attempts < 5 else "failed"
            event.last_error = "" if result.ok else result.error[:200]
            event.claimed_at = None
            event.next_attempt_at = timezone.now() + timedelta(seconds=min(3600, 15 * 2 ** event.attempts))
            event.save(update_fields=["status", "last_error", "claimed_at", "next_attempt_at"])
    # Only inbox replies; existing transactional jobs retain their own dispatcher.
    with all_tenants():
        messages = list(OutboundMessage.objects.filter(purpose="inbox_reply", status__in=["pending", "failed"], next_attempt_at__lte=now).select_related("tenant").order_by("created_at")[:limit])
        OutboundMessage.objects.filter(purpose="inbox_reply", status="sending", claimed_at__lt=now-timedelta(minutes=5)).update(status="failed", claimed_at=None, next_attempt_at=now)
    for message in messages:
        with tenant_context(message.tenant):
            from .models import WhatsAppConversation
            conversation = WhatsAppConversation.objects.filter(phone=message.to_phone).first()
        if not conversation or not conversation.can_reply:
            from .services import _sync_inbox
            message.status = "abandoned"
            message.last_error = "The customer's 24-hour reply window closed before delivery."
            message.save(update_fields=["status", "last_error"])
            _sync_inbox(message)
            continue
        if message.attempts >= 5:
            from .services import _sync_inbox
            message.status = "abandoned"
            message.last_error = "Delivery attempts exhausted. Check connection settings before sending a new reply."
            message.save(update_fields=["status", "last_error"])
            _sync_inbox(message)
        else:
            deliver(message)
    return len(event_ids) + len(messages)
