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
