"""Real inbox workflows with signed webhooks; no live Meta/n8n requests."""
import hashlib
import hmac
import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from django.core import signing
from django.db import connections
from django.utils import timezone
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST, OTHER
from apps.tenancy.models import TenantSecrets
from apps.tenancy.context import tenant_context, all_tenants
from apps.messaging.models import WhatsAppConversation, WhatsAppMessage, WhatsAppReceipt, WhatsAppForwardEvent, OutboundMessage
from apps.messaging.inbox import ingest_meta, ingest_n8n, queue_reply
from apps.messaging.worker import process_inbox_work
from apps.messaging.senders.base import SendResult

APP_SECRET = "test-app-secret-not-a-real-credential"
SYNC_TOKEN = "test-inbox-sync-token-not-a-real-credential"


@pytest.fixture
def connection(kitchens):
    secret = TenantSecrets.objects.create(tenant=kitchens[0], wa_phone_number_id="123456", wa_verify_token="test-verify", wa_provider="n8n", n8n_send_url="https://example.n8n.cloud/webhook/send")
    secret.wa_app_secret = APP_SECRET
    secret.wa_sync_token = SYNC_TOKEN
    secret.n8n_auth_token = "test-workflow-auth"
    secret.save()
    return secret


def incoming(message_id="wamid.incoming", body="Hello, two meals please", phone="919999999999", timestamp=None):
    return {"object": "whatsapp_business_account", "entry": [{"id": "waba-1", "changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "123456"}, "contacts": [{"wa_id": phone, "profile": {"name": "Customer One"}}],
        "messages": [{"from": phone, "id": message_id, "timestamp": str(int((timestamp or timezone.now()).timestamp())), "type": "text", "text": {"body": body}}]}}]}]}


def post_meta(client, payload, host=HOST, secret=APP_SECRET):
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/webhooks/whatsapp/", raw, content_type="application/json", HTTP_HOST=host, HTTP_X_HUB_SIGNATURE_256=signature)


def post_sync(client, payload):
    return client.post("/webhooks/whatsapp/n8n/", json.dumps(payload), content_type="application/json", HTTP_HOST=HOST, HTTP_AUTHORIZATION="Bearer " + SYNC_TOKEN)


def test_meta_verification_rejects_wrong_tokens_and_echoes_challenge(client, connection):
    assert client.get("/webhooks/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "123"}, HTTP_HOST=HOST).status_code == 403
    response = client.get("/webhooks/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "test-verify", "hub.challenge": "123"}, HTTP_HOST=HOST)
    assert response.status_code == 200 and response.content == b"123"


def test_meta_signature_is_required_and_duplicate_delivery_does_not_duplicate_unread(client, connection, kitchens):
    assert post_meta(client, incoming(), secret="wrong").status_code == 403
    assert client.post("/webhooks/whatsapp/", json.dumps(incoming()), content_type="application/json", HTTP_HOST=HOST).status_code == 403
    for _ in range(2):
        assert post_meta(client, incoming()).status_code == 200
    with tenant_context(kitchens[0]):
        assert WhatsAppMessage.objects.count() == 1
        conversation = WhatsAppConversation.objects.get()
        assert conversation.unread_count == 1
        assert conversation.display_name == "Customer One"
        assert conversation.can_reply


def test_webhooks_are_csrf_exempt_but_authenticated(client, connection):
    from django.test import Client
    strict = Client(enforce_csrf_checks=True)
    assert post_meta(strict, incoming()).status_code == 200
    assert post_sync(strict, {"event": "meta", "payload": incoming("wamid.mirror")}).status_code == 200


def test_wrong_phone_id_does_not_write_or_forward_another_kitchens_data(client, connection, kitchens):
    event = incoming()
    event["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "999999"
    assert post_meta(client, event).json()["accepted"] == 0
    with tenant_context(kitchens[0]):
        assert not WhatsAppMessage.objects.exists()
    assert post_meta(client, incoming(), host=OTHER).status_code == 503


def test_invalid_and_oversized_payloads_are_rejected_without_partial_records(client, connection, kitchens):
    bad = incoming()
    bad["entry"][0]["changes"][0]["value"]["messages"].append({"from":"not-a-phone","id":"bad"})
    assert post_meta(client,bad).status_code == 400
    with tenant_context(kitchens[0]):
        assert not WhatsAppMessage.objects.exists()
    assert post_meta(client, {"object": "wrong"}).status_code == 400
    assert post_meta(client, {"object": "whatsapp_business_account", "entry": ["malformed"]}).status_code == 400
    assert client.post("/webhooks/whatsapp/", b"x"*(1024*1024+1), content_type="application/json", HTTP_HOST=HOST).status_code == 413


def test_n8n_outgoing_and_receipts_appear_in_same_customer_thread(client, connection, kitchens):
    assert post_sync(client, {"event": "meta", "payload": incoming()}).status_code == 200
    outgoing = {"event":"outbound", "phone_number_id":"123456", "message_id":"wamid.n8n-out", "message":{"to":"919999999999","type":"text","text":{"body":"Your lunch is confirmed"}}}
    assert client.post("/webhooks/whatsapp/n8n/", json.dumps(outgoing), content_type="application/json", HTTP_HOST=HOST).status_code == 403
    # Receipts can arrive before n8n copies the outgoing body.
    receipt = incoming(); value = receipt["entry"][0]["changes"][0]["value"]
    value.pop("messages"); value["statuses"]=[{"id":"wamid.n8n-out","status":"read","recipient_id":"919999999999","timestamp":str(int(timezone.now().timestamp()))}]
    assert post_meta(client,receipt).status_code == 200
    for _ in range(2):
        assert post_sync(client,outgoing).status_code == 200
    with tenant_context(kitchens[0]):
        assert WhatsAppConversation.objects.count() == 1
        message = WhatsAppMessage.objects.get(provider_message_id="wamid.n8n-out")
        assert message.body == "Your lunch is confirmed" and message.direction == "out" and message.status == "read"
    value["statuses"][0]["status"]="sent"
    assert post_meta(client,receipt).status_code == 200
    with tenant_context(kitchens[0]):
        message.refresh_from_db(); assert message.status == "read"


def test_catalog_orders_and_media_keep_structured_message_details(client, connection, kitchens):
    payload = incoming(); messages=payload["entry"][0]["changes"][0]["value"]["messages"]
    messages[0].update(type="order", order={"product_items":[{"product_retailer_id":"meal-1","quantity":2,"item_price":"100","currency":"INR"}]})
    messages.append({"from":"919999999999","id":"wamid.image","timestamp":str(int(timezone.now().timestamp())),"type":"image","image":{"id":"987654","mime_type":"image/jpeg","caption":"Payment screenshot"}})
    assert post_meta(client,payload).status_code == 200
    with tenant_context(kitchens[0]):
        order=WhatsAppMessage.objects.get(kind="order");image=WhatsAppMessage.objects.get(kind="image")
        assert "2 × meal-1" in order.body
        assert image.media_id == "987654" and image.body == "Payment screenshot"


def test_inbox_requires_staff_and_never_leaks_other_tenants(signed_in, client, connection, kitchens):
    assert post_meta(client,incoming()).status_code == 200
    with tenant_context(kitchens[0]):
        conversation=WhatsAppConversation.objects.get()
    assert signed_in.get("/manage/whatsapp/",HTTP_HOST=HOST).status_code == 200
    page=signed_in.get(f"/manage/whatsapp/{conversation.pk}/",HTTP_HOST=HOST)
    assert page.status_code == 200 and b"two meals please" in page.content
    with tenant_context(kitchens[0]):
        conversation.refresh_from_db();assert conversation.unread_count == 0
    assert signed_in.get(f"/manage/whatsapp/{conversation.pk}/",HTTP_HOST=OTHER).status_code == 403
    with tenant_context(kitchens[1]):
        other=WhatsAppConversation.objects.create(phone="919111111111")
        image=WhatsAppMessage.objects.create(conversation=other,direction="in",media_id="123",provider_message_id="rival-image")
    assert signed_in.get(f"/manage/whatsapp/{other.pk}/",HTTP_HOST=HOST).status_code == 404
    assert signed_in.get(f"/manage/whatsapp/messages/{image.pk}/media/",HTTP_HOST=HOST).status_code == 404
    poll=signed_in.get(f"/manage/whatsapp/{conversation.pk}/?poll=1",HTTP_HOST=HOST)
    assert poll.status_code == 200 and "two meals please" in poll.json()["messages"]


def test_reply_queues_once_then_worker_uses_existing_n8n_sender(signed_in, client, connection, kitchens, owner, monkeypatch):
    assert post_meta(client,incoming()).status_code == 200
    with tenant_context(kitchens[0]):
        conversation=WhatsAppConversation.objects.get()
    page=signed_in.get(f"/manage/whatsapp/{conversation.pk}/",HTTP_HOST=HOST)
    token=page.context["reply_token"]
    with patch("apps.messaging.services.sender_for") as factory:
        factory.return_value.send.return_value=SendResult.sent("wamid.staff-reply")
        for _ in range(2):
            assert signed_in.post(f"/manage/whatsapp/{conversation.pk}/reply/",{"token":token,"body":"We will deliver soon"},HTTP_HOST=HOST).status_code == 302
        with tenant_context(kitchens[0]):
            assert OutboundMessage.objects.count() == 1
            assert WhatsAppMessage.objects.filter(direction="out").count() == 1
        process_inbox_work()
        assert factory.return_value.send.call_count == 1
    with tenant_context(kitchens[0]):
        outgoing=WhatsAppMessage.objects.get(direction="out")
        assert outgoing.status == "sent" and outgoing.actor == owner.username
        assert outgoing.provider_message_id == "wamid.staff-reply"


def test_expired_reply_window_and_console_sender_cannot_send(signed_in, client, connection, kitchens):
    post_meta(client,incoming(timestamp=timezone.now()-timedelta(hours=25)))
    with tenant_context(kitchens[0]):
        conversation=WhatsAppConversation.objects.get()
        assert not conversation.can_reply
        with pytest.raises(ValueError,match="24-hour"):
            queue_reply(kitchens[0],conversation,body="Too late",key="test",actor="owner")
        conversation.last_inbound_at=timezone.now();conversation.save()
        connection.wa_provider="console";connection.save()
        with pytest.raises(ValueError,match="real WhatsApp"):
            queue_reply(kitchens[0],conversation,body="Do not pretend",key="test",actor="owner")
        assert not OutboundMessage.objects.exists()


def test_forwarding_is_durable_deduped_and_not_looped_from_n8n(client, connection, kitchens):
    connection.n8n_receive_url="https://example.n8n.cloud/webhook/incoming";connection.save()
    for _ in range(2):assert post_meta(client,incoming()).status_code == 200
    with tenant_context(kitchens[0]):assert WhatsAppForwardEvent.objects.count() == 1
    assert post_sync(client,{"event":"meta","payload":incoming("wamid.from-mirror")}).status_code == 200
    with tenant_context(kitchens[0]):assert WhatsAppForwardEvent.objects.count() == 1
    with patch("apps.messaging.worker.forward_to_n8n",return_value=SendResult.transient("try later")) as forward:
        process_inbox_work(); assert forward.call_count == 1
    with tenant_context(kitchens[0]):
        event=WhatsAppForwardEvent.objects.get();assert event.status=="pending" and event.attempts==1
        event.next_attempt_at=timezone.now();event.save()
    with patch("apps.messaging.worker.forward_to_n8n",return_value=SendResult.sent("ok")):
        process_inbox_work()
    with tenant_context(kitchens[0]):
        event.refresh_from_db();assert event.status=="sent" and event.attempts==2


def test_connection_form_does_not_echo_credentials_or_replace_blank_secrets(signed_in, connection, kitchens):
    page=signed_in.get("/manage/whatsapp/settings/",HTTP_HOST=HOST)
    assert page.status_code==200
    for secret in (APP_SECRET,SYNC_TOKEN,"test-workflow-auth","test-verify"):
        assert secret.encode() not in page.content
    assert set(page.context["form"].fields) == {"phone_number_id", "sync_token"}
    for name in ("provider", "waba_id", "verify_token", "app_secret", "n8n_send_url", "n8n_receive_url", "n8n_auth_token", "meta_token"):
        assert f'name="{name}"'.encode() not in page.content
    data={"phone_number_id":"123456"}
    assert signed_in.post("/manage/whatsapp/settings/",data,HTTP_HOST=HOST).status_code==302
    connection.refresh_from_db();assert connection.wa_sync_token==SYNC_TOKEN and connection.wa_app_secret==APP_SECRET
    assert SYNC_TOKEN not in connection._wa_sync_token
    data["n8n_receive_url"]="https://127.0.0.1/private"
    response=signed_in.post("/manage/whatsapp/settings/",data,HTTP_HOST=HOST)
    assert response.status_code==302  # Removed fields cannot change existing integration settings.
    connection.refresh_from_db();assert not connection.n8n_receive_url
    assert connection.wa_provider=="n8n" and connection.n8n_send_url=="https://example.n8n.cloud/webhook/send"


def test_media_download_is_staff_only_and_does_not_redirect_tokens(signed_in, client, connection, kitchens):
    payload=incoming();payload["entry"][0]["changes"][0]["value"]["messages"][0].update(type="image",image={"id":"1234567"})
    post_meta(client,payload)
    with tenant_context(kitchens[0]):message=WhatsAppMessage.objects.get()
    with patch("apps.messaging.senders.inbox_io.download_media",return_value=(b"fake-image","image/jpeg")):
        page=signed_in.get(f"/manage/whatsapp/messages/{message.pk}/media/",HTTP_HOST=HOST)
        assert page.status_code==200 and page["Content-Type"]=="image/jpeg" and page["Cache-Control"]=="private, no-store"
    from django.test import Client
    assert Client().get(f"/manage/whatsapp/messages/{message.pk}/media/",HTTP_HOST=HOST).status_code==302


def test_plain_text_is_escaped_in_conversation_and_reply_requests_need_csrf(signed_in, client, connection, kitchens, owner):
    post_meta(client,incoming(body='<script>alert("x")</script>'))
    with tenant_context(kitchens[0]):conversation=WhatsAppConversation.objects.get()
    page=signed_in.get(f"/manage/whatsapp/{conversation.pk}/",HTTP_HOST=HOST)
    assert b'<script>alert("x")</script>' not in page.content and b'&lt;script&gt;' in page.content
    from django.test import Client
    strict=Client(enforce_csrf_checks=True);strict.force_login(owner)
    assert strict.post(f"/manage/whatsapp/{conversation.pk}/reply/",{"body":"Hi"},HTTP_HOST=HOST).status_code==403


def test_worker_does_not_send_after_a_queued_reply_window_expires(client, connection, kitchens):
    post_meta(client,incoming())
    with tenant_context(kitchens[0]):
        conversation=WhatsAppConversation.objects.get()
        queued=queue_reply(kitchens[0],conversation,body="A reply",key="window-retry",actor="Staff")
        conversation.last_inbound_at=timezone.now()-timedelta(hours=25);conversation.save()
    with patch("apps.messaging.services.sender_for") as sender:
        process_inbox_work()
        sender.assert_not_called()
    queued.refresh_from_db();assert queued.status=="abandoned"


def test_n8n_copy_arriving_before_app_send_finishes_merges_into_one_outgoing_bubble(client, connection, kitchens):
    post_meta(client,incoming())
    with tenant_context(kitchens[0]):
        conversation=WhatsAppConversation.objects.get()
        queued=queue_reply(kitchens[0],conversation,body="A reply",key="send-race",actor="Staff")
    post_sync(client,{"event":"outbound","phone_number_id":"123456","message_id":"wamid.race","message":{"to":"919999999999","type":"text","text":{"body":"A reply"}}})
    from apps.messaging.services import deliver
    with patch("apps.messaging.services.sender_for") as sender:
        sender.return_value.send.return_value=SendResult.sent("wamid.race")
        deliver(queued)
    with tenant_context(kitchens[0]):
        assert WhatsAppMessage.objects.filter(direction="out").count()==1
        message=WhatsAppMessage.objects.get(direction="out")
        assert message.outbound_id==queued.pk and message.actor=="Staff"


def test_media_destination_is_checked_before_forwarding_bearer_credentials(connection, kitchens):
    from apps.messaging.senders.inbox_io import download_media
    connection.wa_token="test-meta-media-token";connection.save()
    with patch("apps.messaging.senders.inbox_io.urllib.request.build_opener") as build:
        build.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"url":"https://attacker.example/steal-token"}'
        with pytest.raises(ValueError,match="unsupported media"):
            download_media(kitchens[0],"123456")
        assert build.return_value.open.call_count==1


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_meta_deliveries_create_one_message_and_one_unread(connection, kitchens):
    def receive(_):
        try:
            ingest_meta(kitchens[0],incoming("wamid.concurrent"))
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(receive,range(2)))
    with tenant_context(kitchens[0]):
        assert WhatsAppMessage.objects.count()==1
        assert WhatsAppConversation.objects.get().unread_count==1



def test_minimal_n8n_connection_requires_initial_token_and_can_receive_without_a_send_workflow(signed_in, kitchens):
    data={"phone_number_id":"123456"}
    response=signed_in.post("/manage/whatsapp/settings/",data,HTTP_HOST=HOST)
    assert response.status_code==200 and "sync_token" in response.context["form"].errors
    data["sync_token"]="new-sync-token-with-at-least-24-characters"
    assert signed_in.post("/manage/whatsapp/settings/",data,HTTP_HOST=HOST).status_code==302
    connection=TenantSecrets.objects.get(tenant=kitchens[0])
    assert connection.wa_sync_token==data["sync_token"]
    assert connection.wa_provider=="console" and not connection.n8n_send_url
    payload={"event":"outbound","phone_number_id":"123456","message_id":"wamid.minimal","message":{"to":"919999999999","type":"text","text":{"body":"n8n replied"}}}
    response=signed_in.post("/webhooks/whatsapp/n8n/",json.dumps(payload),content_type="application/json",HTTP_HOST=HOST,HTTP_AUTHORIZATION="Bearer "+data["sync_token"])
    assert response.status_code==200
    with tenant_context(kitchens[0]):
        assert WhatsAppMessage.objects.get().body=="n8n replied"
