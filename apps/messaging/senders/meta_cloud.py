"""Talks to Meta's Graph API directly. The default, and the fewest moving parts."""
import json
import logging
import urllib.error
import urllib.request

from .base import SendResult

log = logging.getLogger("messaging")

GRAPH_VERSION = "v21.0"
TIMEOUT = 15

# Meta error codes that will never succeed on retry.
PERMANENT_CODES = {
    131009,  # parameter value is not valid (e.g. cta_url label too long)
    131047,  # outside the 24-hour window; needs a template
    131026,  # message undeliverable — not a WhatsApp number
    100,     # malformed request
}


class MetaCloudSender:
    def __init__(self, tenant):
        self.tenant = tenant
        self.secrets = tenant.secrets

    def _url(self):
        return (
            f"https://graph.facebook.com/{GRAPH_VERSION}/"
            f"{self.secrets.wa_phone_number_id}/messages"
        )

    def send(self, message) -> SendResult:
        try:
            body = to_graph_payload(message.to_phone, message.payload)
        except Exception as exc:  # a payload we built wrong is our bug, not Meta's
            return SendResult.permanent(f"Could not build the request: {exc}")

        request = urllib.request.Request(
            self._url(),
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.secrets.wa_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                data = json.loads(response.read().decode() or "{}")
            wamid = (data.get("messages") or [{}])[0].get("id", "")
            return SendResult.sent(wamid)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            code = _error_code(raw)
            detail = f"HTTP {exc.code} (code {code}): {raw[:400]}"
            log.warning("[whatsapp:%s] send failed — %s", self.tenant.slug, detail)
            if code in PERMANENT_CODES or 400 <= exc.code < 500 and exc.code != 429:
                return SendResult.permanent(detail)
            return SendResult.transient(detail)
        except Exception as exc:
            return SendResult.transient(f"{type(exc).__name__}: {exc}")


def _error_code(raw: str) -> int | None:
    try:
        return json.loads(raw).get("error", {}).get("code")
    except Exception:
        return None


def to_graph_payload(to_phone: str, payload: dict) -> dict:
    """Translate a provider-agnostic payload into Meta's wire format.

    Kept as a module function so it can be unit-tested without a tenant, and
    reused by the n8n sender when n8n is configured to forward verbatim.
    """
    kind = payload["kind"]
    base = {"messaging_product": "whatsapp", "to": to_phone}

    if kind == "text":
        return {**base, "type": "text", "text": {"body": payload["body"]}}

    if kind == "buttons":
        return {
            **base, "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": payload["body"]},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                        for b in payload["buttons"]
                    ]
                },
            },
        }

    if kind == "cta_url":
        return {
            **base, "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {"text": payload["body"]},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": payload["label"],
                        "url": payload["url"],
                    },
                },
            },
        }

    if kind == "list":
        return {
            **base, "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": payload["body"]},
                "action": {"button": payload["button"], "sections": payload["sections"]},
            },
        }

    if kind == "document":
        return {
            **base, "type": "document",
            "document": {
                "link": payload["url"],
                "filename": payload["filename"],
                "caption": payload.get("caption", ""),
            },
        }

    if kind == "template":
        components = []
        if payload.get("params"):
            components = [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in payload["params"]],
            }]
        return {
            **base, "type": "template",
            "template": {
                "name": payload["name"],
                "language": {"code": payload.get("language", "en")},
                "components": components,
            },
        }

    raise ValueError(f"Unknown payload kind: {kind!r}")
