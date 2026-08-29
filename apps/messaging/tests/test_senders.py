"""Senders are drivers. Swapping one must change how a message leaves and
nothing else — not its content, not whether we know it was sent."""
import json
from unittest.mock import patch

import pytest

from apps.messaging import payloads as p
from apps.messaging import services
from apps.messaging.models import MessageStatus
from apps.messaging.senders import sender_for
from apps.messaging.senders.meta_cloud import MetaCloudSender, to_graph_payload
from apps.messaging.senders.n8n import N8nSender
from apps.tenancy.context import tenant_context
from apps.tenancy.models import MessageProvider, Tenant, TenantSecrets


@pytest.fixture
def kitchen(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    TenantSecrets.objects.create(
        tenant=t,
        wa_provider=MessageProvider.META_CLOUD,
        wa_phone_number_id="906383375891144",
        n8n_send_url="https://automation.seerbusiness.com/webhook/wa-send",
    )
    t.secrets.wa_token = "test-token"
    t.secrets.n8n_auth_token = "shared-secret"
    t.secrets.save()
    t.refresh_from_db()
    return t


class FakeResponse:
    def __init__(self, body): self._body = body.encode()
    def read(self): return self._body
    def __enter__(self): return self
    def __exit__(self, *a): return False


# --- wire format ------------------------------------------------------------

def test_text_translates_to_metas_format():
    assert to_graph_payload("9195", p.text("Hi")) == {
        "messaging_product": "whatsapp", "to": "9195",
        "type": "text", "text": {"body": "Hi"},
    }


def test_cta_url_uses_display_text_which_is_the_20_char_field():
    body = to_graph_payload("9195", p.cta_url("Order", "https://x.in", "View Catalog"))
    params = body["interactive"]["action"]["parameters"]
    assert params["display_text"] == "View Catalog"
    assert params["url"] == "https://x.in"
    assert len(params["display_text"]) <= 20


def test_buttons_translate_to_reply_buttons():
    body = to_graph_payload("9195", p.buttons("Pick", [("a", "Website"), ("b", "WhatsApp")]))
    ids = [b["reply"]["id"] for b in body["interactive"]["action"]["buttons"]]
    assert ids == ["a", "b"]


def test_document_carries_a_link_and_filename():
    body = to_graph_payload("9195", p.document("https://x.in/i.pdf", "invoice.pdf", "Your bill"))
    assert body["document"]["filename"] == "invoice.pdf"


def test_an_unknown_payload_kind_is_a_programming_error():
    with pytest.raises(ValueError):
        to_graph_payload("9195", {"kind": "smoke-signal"})


# --- the drivers ------------------------------------------------------------

def test_meta_sender_posts_to_the_graph_api(kitchen):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode())
        return FakeResponse('{"messages":[{"id":"wamid.ABC"}]}')

    with tenant_context(kitchen):
        msg = services.queue(kitchen, "9195", p.text("Hi"))
        with patch("urllib.request.urlopen", fake_urlopen):
            result = MetaCloudSender(kitchen).send(msg)

    assert result.ok and result.provider_message_id == "wamid.ABC"
    assert "906383375891144/messages" in captured["url"]
    assert captured["auth"] == "Bearer test-token"
    assert captured["body"]["text"]["body"] == "Hi"


def test_meta_permanent_errors_are_not_retried(kitchen):
    """131009 is what Meta returns for an over-length cta_url label."""
    import urllib.error

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {},
            __import__("io").BytesIO(b'{"error":{"code":131009}}'),
        )

    with tenant_context(kitchen):
        msg = services.queue(kitchen, "9195", p.text("Hi"))
        with patch("urllib.request.urlopen", fake_urlopen):
            result = MetaCloudSender(kitchen).send(msg)
    assert not result.ok and not result.retryable


def test_n8n_sender_posts_an_envelope_n8n_can_forward_verbatim(kitchen):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode())
        return FakeResponse('{"wamid":"wamid.FROM_N8N"}')

    with tenant_context(kitchen):
        msg = services.queue(kitchen, "9195", p.text("Hi"), purpose="order_confirmed")
        with patch("urllib.request.urlopen", fake_urlopen):
            result = N8nSender(kitchen).send(msg)

    assert result.ok and result.provider_message_id == "wamid.FROM_N8N"
    assert captured["url"].endswith("/webhook/wa-send")
    assert captured["auth"] == "Bearer shared-secret"

    body = captured["body"]
    assert body["tenant"] == "annam"
    assert body["purpose"] == "order_confirmed"
    # The workflow can stay logic-free: `graph` is ready to POST to Meta as-is.
    assert body["graph"]["messaging_product"] == "whatsapp"
    assert body["graph"]["text"]["body"] == "Hi"


def test_n8n_being_down_delays_a_message_it_never_loses_one(kitchen):
    def fake_urlopen(request, timeout=None):
        raise OSError("connection refused")

    with tenant_context(kitchen):
        kitchen.secrets.wa_provider = MessageProvider.N8N
        kitchen.secrets.save()
        msg = services.queue(kitchen, "9195", p.text("Your invoice"), purpose="invoice")
        with patch("urllib.request.urlopen", fake_urlopen):
            services.deliver(msg)

    msg.refresh_from_db()
    assert msg.status == MessageStatus.FAILED     # not lost — queued for retry
    assert msg.attempts == 1
    assert "connection refused" in msg.last_error


def test_no_n8n_url_configured_is_a_permanent_failure(kitchen):
    with tenant_context(kitchen):
        kitchen.secrets.n8n_send_url = ""
        kitchen.secrets.save()
        msg = services.queue(kitchen, "9195", p.text("Hi"))
        result = N8nSender(kitchen).send(msg)
    assert not result.ok and not result.retryable


# --- the architectural claim ------------------------------------------------

def test_switching_provider_changes_the_hop_and_nothing_else(kitchen):
    """The same call produces the same stored message whichever driver sends it.

    This is the whole point: content, validation, queueing, retries and status
    live in the app. n8n is a delivery choice, not a place logic lives.
    """
    sent_via = {}

    def fake_urlopen(request, timeout=None):
        sent_via["url"] = request.full_url
        return FakeResponse('{"messages":[{"id":"wamid.X"}]}')

    payload = p.cta_url("Your order is ready", "https://annamfood.in", "View Catalog")

    with tenant_context(kitchen):
        kitchen.secrets.wa_provider = MessageProvider.META_CLOUD
        kitchen.secrets.save()
        kitchen.refresh_from_db()
        with patch("urllib.request.urlopen", fake_urlopen):
            direct = services.send_now(kitchen, "9195", payload, purpose="order")
        direct_url = sent_via["url"]

        kitchen.secrets.wa_provider = MessageProvider.N8N
        kitchen.secrets.save()
        kitchen.refresh_from_db()
        with patch("urllib.request.urlopen", fake_urlopen):
            relayed = services.send_now(kitchen, "9195", payload, purpose="order")
        relayed_url = sent_via["url"]

    assert "graph.facebook.com" in direct_url
    assert "automation.seerbusiness.com" in relayed_url
    assert direct.payload == relayed.payload            # identical content
    assert direct.status == relayed.status == MessageStatus.SENT
    assert direct.purpose == relayed.purpose
    assert direct.provider == MessageProvider.META_CLOUD
    assert relayed.provider == MessageProvider.N8N


def test_the_provider_is_chosen_per_tenant(kitchen, db):
    other = Tenant.objects.create(slug="rival", name="Rival", status="active")
    TenantSecrets.objects.create(tenant=other, wa_provider=MessageProvider.N8N,
                                 n8n_send_url="https://example.test/hook")
    assert isinstance(sender_for(kitchen), MetaCloudSender)
    assert isinstance(sender_for(other), N8nSender)


def test_a_tenant_with_no_secrets_falls_back_to_console(db):
    bare = Tenant.objects.create(slug="new", name="Newly provisioned", status="provisioning")
    from apps.messaging.senders import ConsoleSender
    assert isinstance(sender_for(bare), ConsoleSender)
