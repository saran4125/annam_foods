"""Inbox storage, webhook normalization and delivery state; no provider I/O."""
import hashlib
import json
import re
from datetime import datetime, timezone as dt_timezone, timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantSecrets, MessageProvider
from .models import (WhatsAppConversation, WhatsAppMessage, WhatsAppReceipt,
                     WhatsAppForwardEvent, OutboundMessage)


def phone_number(value):
    value = re.sub(r"[\s()+-]", "", str(value or ""))
    if not re.fullmatch(r"[0-9]{7,20}", value):
        raise ValueError("A valid WhatsApp phone number is required.")
    return value


def event_time(value):
    if value in (None, ""):
        return timezone.now()
    try:
        result = datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError) as exc:
        raise ValueError("Invalid message timestamp.") from exc
    if result > timezone.now() + timedelta(minutes=5):
        raise ValueError("Message timestamp is in the future.")
    return result


def describe(message):
    """Readable text for text, media, interactive replies and WhatsApp catalog carts."""
    kind = str(message.get("type") or message.get("kind") or "unsupported")[:30]
    data = message.get(kind) or {}
    if not isinstance(data, dict):
        data = {}
    if kind in ("text", "buttons", "cta_url", "list"):
        text = data.get("body", message.get("body", ""))
    elif kind in ("interactive", "button"):
        reply = data.get("button_reply") or data.get("list_reply") or data
        text = reply.get("title") or reply.get("text") or (data.get("body") or {}).get("text", "") or "Interactive message"
    elif kind == "order":
        lines = ["WhatsApp catalog order"]
        for item in data.get("product_items", [])[:100]:
            lines.append(f'{item.get("quantity", "?")} × {item.get("product_retailer_id", "Item")} · {item.get("currency", "")} {item.get("item_price", "")}')
        if data.get("text"):
            lines.append(str(data["text"]))
        text = "\n".join(lines)
    elif kind == "location":
        text = "Location: " + str(data.get("name") or data.get("address") or "") + f' ({data.get("latitude", "")}, {data.get("longitude", "")})'
    elif kind == "reaction":
        text = "Reaction: " + str(data.get("emoji") or "removed")
    elif kind == "contacts":
        text = "Shared contact: " + ", ".join(str((contact.get("name") or {}).get("formatted_name", "Contact")) for contact in message.get("contacts", [])[:20])
    elif kind == "template":
        text = "Template: " + str(data.get("name") or message.get("name", ""))
    else:
        text = data.get("caption") or message.get("caption") or data.get("filename") or message.get("filename") or kind.replace("_", " ").capitalize()
    # Preserve public media links in outgoing Graph bodies; never fetch arbitrary
    # links with Meta credentials or embed them automatically in the browser.
    media_link = data.get("link") or message.get("url")
    if kind in ("image", "audio", "video", "document", "sticker") and isinstance(media_link, str) and media_link.startswith("https://"):
        text = str(text) + "\n" + media_link
    return {"kind": kind, "body": str(text)[:64000], "media_id": str(data.get("id") or "")[:200],
            "filename": str(data.get("filename") or "")[:200], "mime_type": str(data.get("mime_type") or "")[:100]}


def _apply_receipts(message):
    if not message.provider_message_id or message.direction != "out":
        return
    receipts = WhatsAppReceipt.objects.filter(provider_message_id=message.provider_message_id, phone=message.conversation.phone)
    states = set(receipts.values_list("status", flat=True))
    status = next((state for state in ("read", "delivered", "failed", "sent") if state in states), None)
    if status:
        message.status = status
        message.save(update_fields=["status"])


@transaction.atomic
def record_message(*, phone, direction, provider_id, payload, occurred_at, name="", status=None):
    phone = phone_number(phone)
    if direction not in ("in", "out") or not provider_id or len(provider_id) > 200:
        raise ValueError("Message direction and provider message ID are required.")
    existing = WhatsAppMessage.objects.filter(provider_message_id=provider_id).first()
    if existing:
        if existing.conversation.phone != phone or existing.direction != direction:
            raise ValueError("Message ID belongs to another conversation.")
        return existing
    conversation, _ = WhatsAppConversation.objects.get_or_create(phone=phone)
    conversation = WhatsAppConversation.objects.select_for_update().get(pk=conversation.pk)
    # Recheck after acquiring the conversation lock for duplicate webhook deliveries.
    existing = WhatsAppMessage.objects.filter(provider_message_id=provider_id).first()
    if existing:
        return existing
    message = WhatsAppMessage.objects.create(conversation=conversation, direction=direction,
        provider_message_id=provider_id, payload=payload, occurred_at=occurred_at,
        status=status or ("received" if direction == "in" else "sent"), **describe(payload))
    if name:
        conversation.display_name = str(name)[:120]
    if direction == "in":
        conversation.unread_count += 1
        if not conversation.last_inbound_at or occurred_at > conversation.last_inbound_at:
            conversation.last_inbound_at = occurred_at
    if conversation.messages.count() == 1 or occurred_at >= conversation.last_message_at:
        conversation.last_message_at = occurred_at
        conversation.preview = message.body[:280]
    conversation.save()
    _apply_receipts(message)
    return message


@transaction.atomic
def ingest_meta(tenant, payload, *, forward=False):
    """Accept only this host's configured phone ID, even for multi-phone Meta batches."""
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account" or not isinstance(payload.get("entry"), list):
        raise ValueError("Expected a WhatsApp Business webhook object.")
    secrets = tenant.secrets
    entries, accepted = [], 0
    with tenant_context(tenant):
        for entry in payload["entry"]:
            changes = []
            for change in entry.get("changes", []):
                value = change.get("value") or {}
                if change.get("field") != "messages" or (value.get("metadata") or {}).get("phone_number_id") != secrets.wa_phone_number_id:
                    continue
                if secrets.wa_waba_id and str(entry.get("id")) != secrets.wa_waba_id:
                    continue
                names = {str(contact.get("wa_id")): (contact.get("profile") or {}).get("name", "") for contact in value.get("contacts", [])}
                for incoming in value.get("messages", []):
                    record_message(phone=incoming.get("from"), direction="in", provider_id=str(incoming.get("id") or ""),
                        payload=incoming, occurred_at=event_time(incoming.get("timestamp")), name=names.get(str(incoming.get("from")), ""))
                    accepted += 1
                for receipt in value.get("statuses", []):
                    state = receipt.get("status")
                    if state not in ("sent", "delivered", "read", "failed"):
                        continue
                    message_id = str(receipt.get("id") or "")
                    if not message_id or len(message_id) > 200:
                        raise ValueError("A valid status message ID is required.")
                    phone = phone_number(receipt.get("recipient_id"))
                    WhatsAppReceipt.objects.get_or_create(provider_message_id=message_id, status=state,
                        defaults={"phone": phone, "occurred_at": event_time(receipt.get("timestamp"))})
                    message = WhatsAppMessage.objects.select_related("conversation").filter(provider_message_id=message_id, direction="out").first()
                    if message:
                        _apply_receipts(message)
                    accepted += 1
                changes.append(change)
            if changes:
                entries.append({"id": entry.get("id"), "changes": changes})
        if forward and entries and secrets.n8n_receive_url:
            filtered = {"object": "whatsapp_business_account", "entry": entries}
            digest = hashlib.sha256(json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            WhatsAppForwardEvent.objects.get_or_create(digest=digest, defaults={"payload": filtered})
    return accepted


def ingest_n8n(tenant, data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object.")
    if data.get("event") == "meta":
        return ingest_meta(tenant, data.get("payload"), forward=False)
    if data.get("event") != "outbound" or data.get("phone_number_id") != tenant.secrets.wa_phone_number_id:
        raise ValueError("Expected this kitchen's outbound message or a Meta event.")
    message = data.get("message")
    if not isinstance(message, dict):
        raise ValueError("Include the Graph message body sent by n8n.")
    with tenant_context(tenant):
        record_message(phone=message.get("to"), direction="out", provider_id=str(data.get("message_id") or ""),
            payload=message, occurred_at=event_time(data.get("timestamp")), name=str(data.get("contact_name") or ""))
    return 1


@transaction.atomic
def sync_outbound(outbound):
    """Mirror app-owned outgoing messages into the same customer timeline."""
    with tenant_context(outbound.tenant):
        conversation, _ = WhatsAppConversation.objects.get_or_create(phone=phone_number(outbound.to_phone))
        conversation = WhatsAppConversation.objects.select_for_update().get(pk=conversation.pk)
        # An n8n callback can arrive before the send request returns its message ID.
        by_id = WhatsAppMessage.objects.filter(provider_message_id=outbound.provider_message_id).first() if outbound.provider_message_id else None
        message = WhatsAppMessage.objects.filter(outbound=outbound).first()
        if by_id and (by_id.conversation_id != conversation.pk or by_id.direction != "out"):
            raise ValueError("Provider message ID belongs to another conversation.")
        if by_id and message and by_id.pk != message.pk:
            by_id.delete()
        defaults = {"conversation": conversation, "direction": "out", "payload": outbound.payload,
                    "occurred_at": outbound.created_at, "status": outbound.status,
                    "provider_message_id": outbound.provider_message_id, **describe(outbound.payload)}
        if message:
            for key, value in defaults.items():
                setattr(message, key, value)
            message.save()
        elif by_id:
            message = by_id
            message.outbound = outbound
            message.save(update_fields=["outbound"])
        else:
            message = WhatsAppMessage.objects.create(outbound=outbound, **defaults)
        if outbound.created_at >= conversation.last_message_at or conversation.messages.count() == 1:
            conversation.last_message_at = outbound.created_at
            conversation.preview = message.body[:280]
            conversation.save(update_fields=["last_message_at", "preview"])
        _apply_receipts(message)
        return message


@transaction.atomic
def mark_read(conversation):
    conversation = WhatsAppConversation.objects.select_for_update().get(pk=conversation.pk)
    conversation.unread_count = 0
    conversation.save(update_fields=["unread_count"])


@transaction.atomic
def queue_reply(tenant, conversation, *, body, key, actor):
    from .payloads import text
    from .services import queue
    if conversation.tenant_id != tenant.pk:
        raise ValueError("Conversation does not belong to this kitchen.")
    if not conversation.can_reply:
        raise ValueError("The 24-hour reply window is closed. Ask the customer to message again or use an approved template in your WhatsApp provider.")
    secrets = getattr(tenant, "secrets", None)
    if not secrets or secrets.wa_provider == MessageProvider.CONSOLE or not secrets.whatsapp_is_configured:
        raise ValueError("Configure a real WhatsApp sender in Connection settings before replying.")
    outbound = queue(tenant, conversation.phone, text(body), purpose="inbox_reply", dedupe_key="inbox:" + key)
    message = sync_outbound(outbound)
    if not message.actor:
        message.actor = actor[:120]
        message.save(update_fields=["actor"])
    return outbound
