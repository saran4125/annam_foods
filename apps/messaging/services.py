"""Queueing and dispatch.

Callers say what to send. This module owns everything about getting it there:
persistence, retries, backoff, status and idempotency. No caller ever talks to
a provider directly.
"""
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import MessageStatus, OutboundMessage
from .senders import sender_for

log = logging.getLogger("messaging")

MAX_ATTEMPTS = 5
# Backoff in minutes per attempt. Deliberately gentle at first — most failures
# are a blip — then long enough that a broken token doesn't hammer Meta.
BACKOFF_MINUTES = [0, 1, 5, 20, 60]
STALE_SENDING_AFTER = timedelta(minutes=5)


def queue(tenant, to_phone: str, payload: dict, *, purpose: str = "",
          dedupe_key: str = "") -> OutboundMessage:
    """Record a message for delivery and return the row.

    `dedupe_key` makes the send idempotent: queueing the same key twice
    returns the original row instead of sending twice. Use it anywhere a
    webhook might be redelivered — a payment confirmation, an invoice.
    """
    if dedupe_key:
        existing = OutboundMessage.all_tenants.filter(
            tenant=tenant, dedupe_key=dedupe_key
        ).first()
        if existing:
            return existing
    try:
        with transaction.atomic():
            message = OutboundMessage.all_tenants.create(
                tenant=tenant, to_phone=to_phone, payload=payload,
                purpose=purpose, dedupe_key=dedupe_key,
            )
            _sync_inbox(message)
            return message
    except IntegrityError:
        # Lost a race on the dedupe key: the other writer's row is the answer.
        return OutboundMessage.all_tenants.get(tenant=tenant, dedupe_key=dedupe_key)


def deliver(message: OutboundMessage) -> OutboundMessage:
    """Attempt one delivery. Never raises — failures land on the row."""

    # Claim the row under a database lock. Multiple Huey workers can select
    # the same due row before either starts sending; the locked refresh makes
    # only the first worker transition it to SENDING.
    with transaction.atomic():
        OutboundMessage.all_tenants.select_for_update().get(pk=message.pk)
        message.refresh_from_db()
        if not message.is_deliverable:
            return message

        tenant = message.tenant
        sender = sender_for(tenant)
        provider = getattr(getattr(tenant, "secrets", None), "wa_provider", "console")

        message.status = MessageStatus.SENDING
        message.provider = provider
        message.attempts += 1
        message.claimed_at = timezone.now()
        message.save(update_fields=["status", "provider", "attempts", "claimed_at"])

    try:
        result = sender.send(message)
    except Exception as exc:
        # A sender must return a SendResult, but a bug or a misconfigured
        # secret (wrong SECRETS_KEY) can still throw. Landing it here as
        # permanent means the row is never left stuck in SENDING -- the order
        # survives, the error is visible, and retrying won't fix a code bug.
        message.status = MessageStatus.ABANDONED
        message.claimed_at = None
        message.last_error = f"{type(exc).__name__}: {exc}"
        log.error(
            "[whatsapp:%s] sender raised for message %s: %s",
            tenant.slug, message.pk, message.last_error,
        )
        message.save(update_fields=["status", "last_error", "claimed_at"])
        _sync_inbox(message)
        return message

    if result.ok:
        message.status = MessageStatus.SENT
        message.provider_message_id = result.provider_message_id
        message.sent_at = timezone.now()
        message.last_error = ""
    elif not result.retryable or message.attempts >= MAX_ATTEMPTS:
        message.status = MessageStatus.ABANDONED
        message.last_error = result.error
        log.error(
            "[whatsapp:%s] giving up on message %s after %s attempt(s): %s",
            tenant.slug, message.pk, message.attempts, result.error,
        )
    else:
        message.status = MessageStatus.FAILED
        message.last_error = result.error
        delay = BACKOFF_MINUTES[min(message.attempts, len(BACKOFF_MINUTES) - 1)]
        message.next_attempt_at = timezone.now() + timedelta(minutes=delay)
    message.claimed_at = None

    message.save(update_fields=[
        "status", "provider_message_id", "sent_at", "last_error", "next_attempt_at",
        "claimed_at",
    ])
    _sync_inbox(message)
    return message


def send_now(tenant, to_phone: str, payload: dict, *, purpose: str = "",
             dedupe_key: str = "") -> OutboundMessage:
    """Queue and attempt immediately.

    Convenient for a request that can afford the wait. Anything on a webhook
    path should use `queue()` and let the worker deliver, so the provider's
    latency never delays our own 200.
    """
    return deliver(queue(tenant, to_phone, payload,
                         purpose=purpose, dedupe_key=dedupe_key))


def dispatch_pending(limit: int = 50, tenant=None) -> dict:
    """Worker entry point. Runs across every tenant."""
    from apps.tenancy.context import all_tenants

    now = timezone.now()
    counts = {"sent": 0, "failed": 0, "abandoned": 0}
    with all_tenants():
        # A process can disappear after committing SENDING and before saving a
        # result. Requeue stale claims with the same backoff and attempt cap.
        stale_ids = list(OutboundMessage.objects.filter(
            status=MessageStatus.SENDING,
            claimed_at__lt=now - STALE_SENDING_AFTER,
        ).values_list("pk", flat=True)[:limit])
        for message_id in stale_ids:
            with transaction.atomic():
                stale = OutboundMessage.all_tenants.select_for_update().get(pk=message_id)
                if (stale.status != MessageStatus.SENDING or not stale.claimed_at
                        or stale.claimed_at >= now - STALE_SENDING_AFTER):
                    continue
                stale.claimed_at = None
                stale.last_error = "Recovered a message claim left sending after worker timeout."
                if stale.attempts >= MAX_ATTEMPTS:
                    stale.status = MessageStatus.ABANDONED
                    counts["abandoned"] += 1
                else:
                    stale.status = MessageStatus.FAILED
                    delay = BACKOFF_MINUTES[min(stale.attempts, len(BACKOFF_MINUTES) - 1)]
                    stale.next_attempt_at = now + timedelta(minutes=delay)
                    counts["failed"] += 1
                stale.save(update_fields=["status", "claimed_at", "last_error", "next_attempt_at"])

        query = OutboundMessage.objects.select_related("tenant", "tenant__secrets").filter(
                status__in=[MessageStatus.PENDING, MessageStatus.FAILED],
                next_attempt_at__lte=now,
            )
        if tenant is not None:
            query = query.filter(tenant=tenant)
        due = list(query.order_by("next_attempt_at")[:limit])
        for message in due:
            deliver(message)
            if message.status == MessageStatus.SENT:
                counts["sent"] += 1
            elif message.status == MessageStatus.ABANDONED:
                counts["abandoned"] += 1
            else:
                counts["failed"] += 1
    return counts


def _sync_inbox(message):
    from .inbox import phone_number, sync_outbound
    try:
        phone_number(message.to_phone)
    except ValueError:
        # Older internal/test recipients need not be WhatsApp phone numbers.
        return
    sync_outbound(message)
