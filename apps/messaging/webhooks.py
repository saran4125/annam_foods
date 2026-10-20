"""Public webhook boundary: verification, signature/auth checks, then durable storage."""
import hashlib
import hmac
import json
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import RequestDataTooBig, ValidationError
from .inbox import ingest_meta, ingest_n8n

MAX_BODY = 1024 * 1024


def _connection(request):
    tenant = getattr(request, "tenant", None)
    return getattr(tenant, "secrets", None) if tenant else None


def _body(request):
    if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY:
        raise RequestDataTooBig
    raw = request.body
    if len(raw) > MAX_BODY:
        raise RequestDataTooBig
    return raw


@csrf_exempt
@require_http_methods(["GET", "POST"])
def meta_webhook(request):
    connection = _connection(request)
    if not connection or not connection.wa_phone_number_id:
        return JsonResponse({"error": "WhatsApp is not configured for this host."}, status=503)
    if request.method == "GET":
        token = request.GET.get("hub.verify_token", "")
        if connection.wa_verify_token and request.GET.get("hub.mode") == "subscribe" and hmac.compare_digest(token.encode(), connection.wa_verify_token.encode()):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return JsonResponse({"error": "Verification failed."}, status=403)
    try:
        raw = _body(request)
        secret = connection.wa_app_secret
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), expected):
            return JsonResponse({"error": "Invalid webhook signature."}, status=403)
        count = ingest_meta(request.tenant, json.loads(raw), forward=True)
    except RequestDataTooBig:
        return JsonResponse({"error": "Payload too large."}, status=413)
    except RuntimeError:
        return JsonResponse({"error": "Connection secrets could not be read. Check server encryption settings."}, status=503)
    except (ValueError, TypeError, AttributeError, KeyError, ValidationError):
        return JsonResponse({"error": "Invalid WhatsApp event."}, status=400)
    return JsonResponse({"ok": True, "accepted": count})


@csrf_exempt
@require_http_methods(["POST"])
def n8n_sync(request):
    connection = _connection(request)
    if not connection or not connection.wa_phone_number_id:
        return JsonResponse({"error": "WhatsApp is not configured for this host."}, status=503)
    try:
        token = connection.wa_sync_token
        authorization = request.headers.get("Authorization", "")
        if not token or not hmac.compare_digest(authorization, "Bearer " + token):
            return JsonResponse({"error": "Unauthorized."}, status=403)
        count = ingest_n8n(request.tenant, json.loads(_body(request)))
    except RequestDataTooBig:
        return JsonResponse({"error": "Payload too large."}, status=413)
    except RuntimeError:
        return JsonResponse({"error": "Connection secrets could not be read."}, status=503)
    except (ValueError, TypeError, AttributeError, KeyError, ValidationError):
        return JsonResponse({"error": "Invalid inbox sync event."}, status=400)
    return JsonResponse({"ok": True, "accepted": count})
