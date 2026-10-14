import pytest

from apps.jobs.services import send_due_messages
from apps.messaging import services as messaging_services
from apps.messaging.models import MessageStatus
from apps.messaging.payloads import text
from apps.messaging.senders.base import SendResult
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantConfig


@pytest.mark.django_db
def test_message_sweep_continues_after_a_tenant_timezone_error(monkeypatch, caplog):
    broken = Tenant.objects.create(slug="broken-messages", name="Broken Messages")
    TenantConfig.objects.filter(tenant=broken).update(timezone="Invalid/Zone")
    healthy = Tenant.objects.create(slug="healthy-messages", name="Healthy Messages")
    with tenant_context(healthy):
        message = messaging_services.queue(healthy, "9195", text("hello"))

    class Sender:
        def send(self, message):
            return SendResult.sent("wamid.ok")

    monkeypatch.setattr(messaging_services, "sender_for", lambda tenant: Sender())
    send_due_messages()

    message.refresh_from_db()
    assert message.status == MessageStatus.SENT
    assert "broken-messages" in caplog.text


@pytest.mark.django_db
def test_message_sweep_skips_suspended_and_cancelled_tenants(monkeypatch):
    sent = []
    suspended = Tenant.objects.create(slug="suspended", name="Suspended", status="suspended")
    cancelled = Tenant.objects.create(slug="cancelled", name="Cancelled", status="cancelled")
    active = Tenant.objects.create(slug="active", name="Active", status="active")
    for tenant in (suspended, cancelled, active):
        with tenant_context(tenant):
            messaging_services.queue(tenant, "9195", text(tenant.slug))

    class Sender:
        def send(self, message):
            sent.append(message.tenant_id)
            return SendResult.sent("wamid.ok")

    monkeypatch.setattr(messaging_services, "sender_for", lambda tenant: Sender())
    send_due_messages()
    assert sent == [active.pk]
