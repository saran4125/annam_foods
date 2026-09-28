"""Hands the message to n8n, which performs the actual WhatsApp send.

Use this when a tenant's sending should stay inside an n8n workflow -- an
existing setup you don't want to disturb, a client on a different BSP, or
somewhere you want the send visible in n8n's execution log.

What does NOT move to n8n: deciding what to say, validating it, queueing it,
retrying it, or knowing whether it went. Those stay here, so a dead n8n
delays a message instead of losing one.
"""
import json
import logging
import urllib.error
import urllib.request

from .base import SendResult
from .meta_cloud import to_graph_payload

log = logging.getLogger("messaging")
TIMEOUT = 20


class N8nSender:
    def __init__(self, tenant):
        self.tenant = tenant
        self.secrets = tenant.secrets

    def send(self, message) -> SendResult:
        url = self.secrets.n8n_send_url
        if not url:
            return SendResult.permanent("No n8n send URL configured for this tenant.")

        envelope = {
            "tenant": self.tenant.slug,
            "to": message.to_phone,
            "purpose": message.purpose,
            "message_id": message.pk,
            # Both shapes, so the workflow can either read the simple fields or
            # forward `graph` straight to the Graph API with no logic at all.
            "payload": message.payload,
            "graph": to_graph_payload(message.to_phone, message.payload),
        }

        try:
            headers = {"Content-Type": "application/json"}
            token = self.secrets.n8n_auth_token
            if token:
                headers["Authorization"] = f"Bearer {token}"
            request = urllib.request.Request(
                url, data=json.dumps(envelope).encode(),
                headers=headers, method="POST",
            )
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read().decode() or "{}"
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            # A workflow that returns the wamid lets us record it; one that
            # returns nothing still counts as sent on a 2xx.
            return SendResult.sent(str(data.get("message_id") or data.get("wamid") or ""))
        except urllib.error.HTTPError as exc:
            detail = f"n8n returned HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}"
            log.warning("[whatsapp:%s] %s", self.tenant.slug, detail)
            # 4xx from n8n means the workflow rejected it; retrying the same
            # body won't help. 5xx and timeouts are worth another attempt.
            return (SendResult.permanent(detail) if 400 <= exc.code < 500
                    else SendResult.transient(detail))
        except RuntimeError as exc:
            # Rotated or wrong SECRETS_KEY. Permanent, not retried -- an
            # operator must fix the key, not the worker wait out a backoff.
            return SendResult.permanent(f"Secret could not be read: {exc}")
        except Exception as exc:
            return SendResult.transient(f"{type(exc).__name__}: {exc}")
