from django.contrib import admin

from apps.tenancy.adminbase import UnscopedAdmin

from .models import OutboundMessage


@admin.register(OutboundMessage)
class OutboundMessageAdmin(UnscopedAdmin):
    """One place to answer "did the customer get it?" — whichever provider sent it."""

    list_display = ("to_phone", "tenant", "purpose", "kind", "status",
                    "provider", "attempts", "created_at", "sent_at")
    list_filter = ("tenant", "status", "provider", "purpose")
    search_fields = ("to_phone", "provider_message_id", "dedupe_key")
    readonly_fields = ("created_at", "sent_at", "attempts", "last_error",
                       "provider_message_id", "payload")

    @admin.display(description="kind")
    def kind(self, obj):
        return obj.payload.get("kind", "")
