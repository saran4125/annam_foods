"""Provider I/O for inbox forwarding and authenticated media. Never called in webhooks."""
import ipaddress
import json
import socket
import urllib.request
from urllib.parse import urlsplit
from .base import SendResult
from .meta_cloud import GRAPH_VERSION


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_n8n_url(url):
    from apps.messaging.connection import validate_webhook_url
    validate_webhook_url(url)
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(record[4][0]).is_global for record in addresses):
        raise ValueError("n8n must resolve to a public address.")


def forward_to_n8n(event):
    try:
        connection = event.tenant.secrets
        if not connection.n8n_receive_url:
            return SendResult.permanent("No n8n automation receive URL configured.")
        public_n8n_url(connection.n8n_receive_url)
        headers = {"Content-Type": "application/json", "X-SeerKitchen-Event-ID": event.digest}
        if connection.n8n_auth_token:
            headers["Authorization"] = "Bearer " + connection.n8n_auth_token
        request = urllib.request.Request(connection.n8n_receive_url, data=json.dumps(event.payload).encode(), headers=headers, method="POST")
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            response.read(1024)
        return SendResult.sent(event.digest)
    except urllib.error.HTTPError as exc:
        return SendResult.permanent(f"n8n HTTP {exc.code}") if 400 <= exc.code < 500 and exc.code != 429 else SendResult.transient(f"n8n HTTP {exc.code}")
    except (ValueError, RuntimeError) as exc:
        return SendResult.permanent("Check the n8n URL, authentication and encryption settings.")
    except Exception:
        return SendResult.transient("n8n could not be reached. The event will be retried.")


def download_media(tenant, media_id):
    token = tenant.secrets.wa_token
    if not token:
        raise ValueError("Attachment preview is not connected. View this attachment in WhatsApp.")
    if not str(media_id).isdigit():
        raise ValueError("Invalid media identifier.")
    opener = urllib.request.build_opener(NoRedirect)
    headers = {"Authorization": "Bearer " + token}
    request = urllib.request.Request(f"https://graph.facebook.com/{GRAPH_VERSION}/{media_id}", headers=headers)
    with opener.open(request, timeout=15) as response:
        metadata = json.loads(response.read(65536))
    parsed = urlsplit(metadata.get("url", ""))
    host = (parsed.hostname or "").lower()
    allowed = (".facebook.com", ".fbcdn.net", ".whatsapp.net", ".fbsbx.com")
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or not host.endswith(allowed):
        raise ValueError("Meta returned an unsupported media destination.")
    with opener.open(urllib.request.Request(metadata["url"], headers=headers), timeout=20) as response:
        content = response.read(16 * 1024 * 1024 + 1)
        mime = response.headers.get_content_type()
    if len(content) > 16 * 1024 * 1024:
        raise ValueError("This attachment is too large to preview (16 MB limit).")
    return content, mime
