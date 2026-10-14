"""Queueing, retries and idempotency — the parts that stay in the app no
matter which provider does the final hop."""
import pytest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock
from django.db import close_old_connections, connections
from django.utils import timezone

from apps.messaging import payloads as p
from apps.messaging import services
from apps.messaging.models import MessageStatus, OutboundMessage
from apps.messaging.senders.base import SendResult
from apps.tenancy.context import all_tenants, tenant_context
from apps.tenancy.models import MessageProvider, Tenant, TenantSecrets


@pytest.fixture
def kitchen(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    TenantSecrets.objects.create(tenant=t, wa_provider=MessageProvider.CONSOLE)
    return t


class FakeSender:
    """Scripted results, so retry behaviour can be tested without a network."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def __call__(self, tenant):
        return self

    def send(self, message):
        self.calls += 1
        return self.results.pop(0) if self.results else SendResult.sent("x")


def use(monkeypatch, sender):
    monkeypatch.setattr(services, "sender_for", sender)


def test_a_queued_message_is_recorded_before_anything_is_sent(kitchen):
    with tenant_context(kitchen):
        msg = services.queue(kitchen, "919551079550", p.text("Hi"), purpose="reply")
        assert msg.status == MessageStatus.PENDING
        assert msg.attempts == 0


def test_a_successful_send_marks_it_sent(kitchen, monkeypatch):
    use(monkeypatch, FakeSender([SendResult.sent("wamid.123")]))
    with tenant_context(kitchen):
        msg = services.send_now(kitchen, "9195", p.text("Hi"))
        assert msg.status == MessageStatus.SENT
        assert msg.provider_message_id == "wamid.123"
        assert msg.sent_at is not None


def test_a_transient_failure_is_retried_later(kitchen, monkeypatch):
    use(monkeypatch, FakeSender([SendResult.transient("network blip")]))
    with tenant_context(kitchen):
        msg = services.send_now(kitchen, "9195", p.text("Hi"))
        assert msg.status == MessageStatus.FAILED
        assert msg.attempts == 1
        assert msg.next_attempt_at > timezone.now()
        assert "blip" in msg.last_error


def test_a_permanent_failure_is_not_retried(kitchen, monkeypatch):
    """A 26-character button label will fail identically forever."""
    use(monkeypatch, FakeSender([SendResult.permanent("code 131009")]))
    with tenant_context(kitchen):
        msg = services.send_now(kitchen, "9195", p.text("Hi"))
        assert msg.status == MessageStatus.ABANDONED
        assert msg.attempts == 1


def test_retries_give_up_after_the_maximum(kitchen, monkeypatch):
    sender = FakeSender([SendResult.transient("down")] * services.MAX_ATTEMPTS)
    use(monkeypatch, sender)
    with tenant_context(kitchen):
        msg = services.queue(kitchen, "9195", p.text("Hi"))
        for _ in range(services.MAX_ATTEMPTS):
            msg.next_attempt_at = timezone.now()
            msg.save(update_fields=["next_attempt_at"])
            services.deliver(msg)
        assert msg.status == MessageStatus.ABANDONED
        assert msg.attempts == services.MAX_ATTEMPTS


def test_a_dedupe_key_sends_only_once(kitchen):
    """A redelivered payment webhook must not send two invoices."""
    with tenant_context(kitchen):
        a = services.queue(kitchen, "9195", p.text("Paid"), dedupe_key="invoice-42")
        b = services.queue(kitchen, "9195", p.text("Paid"), dedupe_key="invoice-42")
        assert a.pk == b.pk
        assert OutboundMessage.objects.filter(dedupe_key="invoice-42").count() == 1


def test_messages_without_a_dedupe_key_are_independent(kitchen):
    with tenant_context(kitchen):
        services.queue(kitchen, "9195", p.text("One"))
        services.queue(kitchen, "9195", p.text("Two"))
        assert OutboundMessage.objects.count() == 2


def test_the_worker_only_picks_up_messages_that_are_due(kitchen, monkeypatch):
    use(monkeypatch, FakeSender([]))
    with tenant_context(kitchen):
        due = services.queue(kitchen, "9195", p.text("now"))
        later = services.queue(kitchen, "9195", p.text("later"))
        later.next_attempt_at = timezone.now() + timezone.timedelta(hours=1)
        later.save(update_fields=["next_attempt_at"])

    counts = services.dispatch_pending()
    assert counts["sent"] == 1
    with tenant_context(kitchen):
        assert OutboundMessage.objects.get(pk=due.pk).status == MessageStatus.SENT
        assert OutboundMessage.objects.get(pk=later.pk).status == MessageStatus.PENDING


def test_a_stale_sending_claim_is_retried_and_a_fresh_claim_is_left_alone(kitchen, monkeypatch):
    use(monkeypatch, FakeSender([]))
    with tenant_context(kitchen):
        stale = services.queue(kitchen, "9195", p.text("stale"))
        stale.status = MessageStatus.SENDING
        stale.attempts = 1
        stale.claimed_at = timezone.now() - services.STALE_SENDING_AFTER - timedelta(seconds=1)
        stale.save(update_fields=["status", "attempts", "claimed_at"])
        fresh = services.queue(kitchen, "9195", p.text("fresh"))
        fresh.status = MessageStatus.SENDING
        fresh.attempts = 1
        fresh.claimed_at = timezone.now()
        fresh.save(update_fields=["status", "attempts", "claimed_at"])

    counts = services.dispatch_pending()
    with tenant_context(kitchen):
        stale.refresh_from_db()
        fresh.refresh_from_db()
        assert stale.status == MessageStatus.FAILED
        assert stale.claimed_at is None
        assert "Recovered" in stale.last_error
        assert fresh.status == MessageStatus.SENDING
        assert counts["failed"] == 1


@pytest.mark.django_db(transaction=True)
def test_two_workers_claim_a_message_only_once(kitchen, monkeypatch):
    assert connections["default"].vendor == "postgresql"

    class CountingSender:
        def __init__(self):
            self.calls = 0
            self.lock = Lock()

        def send(self, message):
            with self.lock:
                self.calls += 1
            return SendResult.sent("wamid.once")

    sender = CountingSender()
    use(monkeypatch, lambda tenant: sender)
    with tenant_context(kitchen):
        message = services.queue(kitchen, "9195", p.text("once"))

    def attempt():
        close_old_connections()
        try:
            candidate = OutboundMessage.all_tenants.get(pk=message.pk)
            return services.deliver(candidate).status
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: attempt(), range(2)))
    message.refresh_from_db()
    assert statuses.count(MessageStatus.SENT) == 2
    assert sender.calls == 1
    assert message.attempts == 1


def test_the_worker_runs_across_every_tenant(kitchen, monkeypatch, db):
    other = Tenant.objects.create(slug="rival", name="Rival", status="active")
    TenantSecrets.objects.create(tenant=other, wa_provider=MessageProvider.CONSOLE)
    use(monkeypatch, FakeSender([]))
    with tenant_context(kitchen):
        services.queue(kitchen, "9111", p.text("a"))
    with tenant_context(other):
        services.queue(other, "9222", p.text("b"))

    assert services.dispatch_pending()["sent"] == 2


def test_messages_do_not_leak_between_kitchens(kitchen, db):
    other = Tenant.objects.create(slug="rival", name="Rival", status="active")
    with tenant_context(kitchen):
        services.queue(kitchen, "9111", p.text("private"))
    with tenant_context(other):
        assert OutboundMessage.objects.count() == 0
    with all_tenants():
        assert OutboundMessage.objects.count() == 1


def test_a_sender_that_raises_does_not_stick_the_message_in_sending(kitchen, monkeypatch):
    """A bug or a wrong SECRETS_KEY must not leave a row stuck in SENDING,
    which is deliverable-never and would silently stop a message for good."""

    class ExplodingSender:
        def __init__(self, tenant):
            self.tenant = tenant

        def send(self, message):
            raise RuntimeError("Could not decrypt a tenant secret. Wrong SECRETS_KEY?")

    monkeypatch.setattr(services, "sender_for", ExplodingSender)
    with tenant_context(kitchen):
        msg = services.queue(kitchen, "9195", p.text("Your invoice"), purpose="invoice")
        services.deliver(msg)

    msg.refresh_from_db()
    assert msg.status == MessageStatus.ABANDONED
    assert "Wrong SECRETS_KEY" in msg.last_error
    # A terminal state: a later worker run must not pick it up again.
    assert not msg.is_deliverable


def test_a_wrong_key_does_not_abort_the_whole_batch(kitchen, monkeypatch, db):
    """One tenant with a broken key must not stop the worker from sending the
    rest of the batch."""

    class ExplodingSender:
        def __init__(self, tenant):
            self.tenant = tenant

        def send(self, message):
            raise RuntimeError("Could not decrypt a tenant secret. Wrong SECRETS_KEY?")

    class HealthySender:
        def __init__(self, tenant):
            self.tenant = tenant

        def send(self, message):
            return SendResult.sent("wamid.ok")

    def per_tenant(tenant):
        return ExplodingSender(tenant) if tenant.slug == "annam" else HealthySender(tenant)

    other = Tenant.objects.create(slug="rival", name="Rival", status="active")
    TenantSecrets.objects.create(tenant=other, wa_provider=MessageProvider.CONSOLE)
    monkeypatch.setattr(services, "sender_for", per_tenant)
    with tenant_context(kitchen):
        services.queue(kitchen, "9111", p.text("a"))
    with tenant_context(other):
        services.queue(other, "9222", p.text("b"))

    counts = services.dispatch_pending()
    assert counts["abandoned"] == 1
    assert counts["sent"] == 1
