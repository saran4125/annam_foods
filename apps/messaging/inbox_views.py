"""Staff-only WhatsApp conversations, replies, protected media and connection settings."""
import uuid
from urllib.parse import urlencode
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from apps.owner.access import owner_required
from apps.tenancy.models import TenantSecrets
from .connection import WhatsAppConnectionForm
from .inbox import mark_read, queue_reply, sync_outbound
from .models import WhatsAppConversation, WhatsAppMessage, OutboundMessage


def _context(request, pk=None):
    query = request.GET.get("q", "").strip()[:100]
    conversations = WhatsAppConversation.objects.all()
    if query:
        conversations = conversations.filter(Q(phone__icontains=query) | Q(display_name__icontains=query))
    selected = get_object_or_404(WhatsAppConversation.objects, pk=pk) if pk else None
    conversation_page = Paginator(conversations, 30).get_page(request.GET.get("contacts_page"))
    message_page = None
    if selected:
        message_page = Paginator(selected.messages.select_related("outbound").order_by("-occurred_at", "-pk"), 50).get_page(request.GET.get("page"))
        if message_page.number == 1:
            mark_read(selected)
    connection = getattr(request.tenant, "secrets", None)
    return {"conversations": conversation_page, "selected": selected, "message_page": message_page,
            "chat_messages": list(reversed(message_page.object_list)) if message_page else [], "query": query,
            "reply_token": signing.dumps({"tenant": request.tenant.pk, "conversation": pk, "user": request.user.pk, "key": uuid.uuid4().hex}, salt="inbox-reply"),
            "reply_ready": bool(connection and connection.wa_provider != "console" and connection.whatsapp_is_configured),
            "has_connection": bool(connection and connection.wa_phone_number_id),
            "media_ready": bool(connection and connection._wa_token),
            "unread_total": WhatsAppConversation.objects.aggregate(n=Sum("unread_count"))["n"] or 0}


@owner_required
@never_cache
def inbox(request, pk=None):
    # Backfill the recent send history once, including messages queued before inbox existed.
    if not WhatsAppMessage.objects.exists():
        for outbound in OutboundMessage.objects.order_by("-created_at")[:200]:
            try:
                sync_outbound(outbound)
            except ValueError:
                pass
    context = _context(request, pk)
    if request.GET.get("poll") == "1":
        return JsonResponse({"contacts": render_to_string("messaging/_contacts.html", context, request=request),
                             "messages": render_to_string("messaging/_messages.html", context, request=request),
                             "unread_total": context["unread_total"],
                             "window_open": bool(context["selected"] and context["selected"].can_reply),
                             "can_reply": bool(context["selected"] and context["selected"].can_reply and context["reply_ready"])})
    return render(request, "messaging/inbox.html", context)


@owner_required
@require_POST
def reply(request, pk):
    conversation = get_object_or_404(WhatsAppConversation.objects, pk=pk)
    try:
        token = signing.loads(request.POST.get("token", ""), salt="inbox-reply", max_age=86400)
        if token["tenant"] != request.tenant.pk or token["conversation"] != pk or token["user"] != request.user.pk:
            raise ValueError("The reply form belongs to another conversation. Reload and try again.")
        queue_reply(request.tenant, conversation, body=request.POST.get("body", ""), key=token["key"], actor=request.user.get_username())
    except signing.BadSignature:
        messages.error(request, "This reply form expired or is invalid. Reload and try again.")
    except (ValueError, ValidationError, KeyError):
        messages.error(request, "Reply not queued. Check the 24-hour window, connection settings and message length (1–1024 characters).")
    else:
        messages.success(request, "Reply queued. Delivery status will update in the conversation.")
    return redirect("owner:whatsapp_conversation", pk=pk)


@owner_required
@never_cache
def connection_settings(request):
    connection, _ = TenantSecrets.objects.get_or_create(tenant=request.tenant)
    form = WhatsAppConnectionForm(request.POST if request.method == "POST" else None, connection=connection)
    if request.method == "POST" and form.is_valid():
        try:
            form.save()
        except RuntimeError:
            form.add_error(None, "Connection secrets could not be encrypted. Check SECRETS_KEY on the server.")
        else:
            messages.success(request, "Inbox sync settings saved. Use the endpoint below in n8n.")
            return redirect("owner:whatsapp_settings")
    return render(request, "messaging/settings.html", {
        "form": form,
        "n8n_url": request.build_absolute_uri(reverse("whatsapp_webhooks:n8n")),
        "sync_token_saved": bool(connection._wa_sync_token),
    })


@owner_required
def media(request, pk):
    from .senders.inbox_io import download_media
    message = get_object_or_404(WhatsAppMessage.objects, pk=pk)
    if not message.media_id:
        return HttpResponseBadRequest("This message does not have a downloadable attachment.")
    try:
        content, mime = download_media(request.tenant, message.media_id)
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    except Exception:
        return HttpResponse("Media unavailable. Check the Meta access token or ask the customer to resend expired media.", status=502, content_type="text/plain")
    inline = mime in {"image/jpeg", "image/png", "image/webp", "audio/ogg", "audio/mpeg", "audio/mp4", "video/mp4"}
    response = HttpResponse(content, content_type=mime if inline else "application/octet-stream")
    response["Content-Disposition"] = content_disposition_header(not inline, message.filename or "whatsapp-attachment")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
