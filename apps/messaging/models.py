from django.db import models
from django.utils import timezone

from apps.tenancy.managers import TenantOwnedModel


class MessageStatus(models.TextChoices):
    PENDING = "pending", "Waiting to send"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed, will retry"
    ABANDONED = "abandoned", "Gave up"


class OutboundMessage(TenantOwnedModel):
    """One message the app wants delivered.

    The row is the source of truth about whether a customer heard from us. It
    exists before any provider is called and survives the provider failing, so
    "did the invoice go out?" is always answerable from our own database
    rather than by reading someone else's execution log.
    """

    to_phone = models.CharField(max_length=20, db_index=True)
    payload = models.JSONField()
    purpose = models.CharField(
        max_length=40, blank=True,
        help_text="Why this was sent: order_confirmed, invoice, owner_alert, reply…",
    )

    status = models.CharField(
        max_length=12, choices=MessageStatus.choices, default=MessageStatus.PENDING,
        db_index=True,
    )
    provider = models.CharField(max_length=20, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)

    attempts = models.PositiveSmallIntegerField(default=0)
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)

    dedupe_key = models.CharField(
        max_length=120, blank=True,
        help_text="Set to make a send idempotent — the same key never sends twice.",
    )

    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="uniq_outbound_dedupe_key",
            )
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="idx_outbound_due"),
        ]

    def __str__(self):
        return f"{self.payload.get('kind', '?')} to {self.to_phone} ({self.status})"

    @property
    def is_deliverable(self) -> bool:
        return self.status in {MessageStatus.PENDING, MessageStatus.FAILED}


class WhatsAppConversation(TenantOwnedModel):
    phone = models.CharField(max_length=20)
    display_name = models.CharField(max_length=120, blank=True)
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    preview = models.CharField(max_length=280, blank=True)
    unread_count = models.PositiveIntegerField(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-last_message_at", "-pk"]
        constraints = [models.UniqueConstraint(fields=["tenant", "phone"], name="uniq_wa_conversation_phone")]

    @property
    def can_reply(self):
        from datetime import timedelta
        return bool(self.last_inbound_at and self.last_inbound_at > timezone.now() - timedelta(hours=24))


class WhatsAppMessage(TenantOwnedModel):
    conversation = models.ForeignKey(WhatsAppConversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=8, choices=[("in", "Customer"), ("out", "Kitchen")])
    kind = models.CharField(max_length=30, default="text")
    body = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="received")
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict)
    media_id = models.CharField(max_length=200, blank=True)
    filename = models.CharField(max_length=200, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    outbound = models.OneToOneField(OutboundMessage, on_delete=models.SET_NULL, null=True, blank=True, related_name="inbox_message")
    actor = models.CharField(max_length=120, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["occurred_at", "pk"]
        constraints = [models.UniqueConstraint(fields=["tenant", "provider_message_id"],
                       condition=~models.Q(provider_message_id=""), name="uniq_wa_message_provider_id")]
        indexes = [models.Index(fields=["tenant", "conversation", "occurred_at"], name="idx_wa_conversation_time")]


class WhatsAppReceipt(TenantOwnedModel):
    provider_message_id = models.CharField(max_length=200)
    status = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "provider_message_id", "status"], name="uniq_wa_message_receipt")]


class WhatsAppForwardEvent(TenantOwnedModel):
    """Durable Meta-to-n8n forwarding; webhooks acknowledge without network waits."""
    digest = models.CharField(max_length=64)
    payload = models.JSONField()
    status = models.CharField(max_length=12, default="pending", db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    claimed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta(TenantOwnedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "digest"], name="uniq_wa_forward_event")]
