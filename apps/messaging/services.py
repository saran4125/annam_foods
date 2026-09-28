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
            return OutboundMessage.all_tenants.create(
                tenant=tenant, to_phone=to_phone, payload=payload,
                purpose=purpose, dedupe_key=dedupe_key,
            )
    except IntegrityError:
        # Lost a race on the dedupe key: the other writer's row is the answer.
        return OutboundMessage.all_tenants.get(tenant=tenant, dedupe_key=dedupe_key)


def deliver(message: OutboundMessage) -> OutboundMessage:
    """Attempt one delivery. Never raises — failures land on the row."""
    if not message.is_deliverable:
        return message

    tenant = message.tenant
    sender = sender_for(tenant)
    provider = getattr(getattr(tenant, "secrets", None), "wa_provider", "console")

    message.status = MessageStatus.SENDING
    message.provider = provider
    message.attempts += 1
    message.save(update_fields=["status", "provider", "attempts"])

    try:
        result = sender.send(message)
    except Exception as exc:
        # A sender must return a SendResult, but a bug or a misconfigured
        # secret (wrong SECRETS_KEY) can still throw. Landing it here as
        # permanent means the row is never left stuck in SENDING -- the order
        # survives, the error is visible, and retrying won't fix a code bug.
        message.status = MessageStatus.ABANDONED
        message.last_error = f"{type(exc).__name__}: {exc}"
        log.error(
            "[whatsapp:%s] sender raised for message %s: %s",
            tenant.slug, message.pk, message.last_error,
        )
        message.save(update_fields=["status", "last_error"])
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

    message.save(update_fields=[
        "status", "provider_message_id", "sent_at", "last_error", "next_attempt_at",
    ])
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
