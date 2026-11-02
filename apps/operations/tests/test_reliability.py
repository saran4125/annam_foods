from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from apps.owner.tests.test_owner import kitchens,owner,signed_in,HOST
from apps.tenancy.context import tenant_context
from apps.operations.models import WorkerPulse
from apps.operations.health import pulse_worker


def test_readiness_checks_database_and_requires_fresh_worker_without_exposing_internals(client,kitchens,settings):
    settings.REQUIRE_WORKER_HEARTBEAT=True;settings.READINESS_CHECK_STORAGE=False;settings.STORE_SLUG='annam'
    assert client.get('/readyz',HTTP_HOST='probe.example.test').status_code==503
    pulse_worker()
    response=client.get('/readyz',HTTP_HOST='probe.example.test')
    assert response.status_code==200 and response.json()=={'status':'ok'} and 'no-store' in response['Cache-Control']
    with tenant_context(kitchens[0]):WorkerPulse.objects.update(updated_at=timezone.now()-timedelta(minutes=5))
    assert client.get('/readyz',HTTP_HOST='probe.example.test').status_code==503
    assert client.get('/healthz',HTTP_HOST='probe.example.test').status_code==200


def test_storage_failure_makes_readiness_unavailable(client,kitchens,settings):
    settings.READINESS_CHECK_STORAGE=True;settings.REQUIRE_WORKER_HEARTBEAT=False
    with patch('apps.operations.health.storage_writable',side_effect=OSError('private-path')):
        response=client.get('/readyz',HTTP_HOST='probe.example.test')
    assert response.status_code==503 and b'private-path' not in response.content


def test_inbox_worker_retries_iteration_after_error_without_marking_it_healthy(monkeypatch):
    from apps.messaging.management.commands.run_whatsapp_worker import Command
    import threading
    stop=threading.Event();waits=[]
    def wait(seconds):
        waits.append(seconds)
        if len(waits)==2:stop.set()
    monkeypatch.setattr(stop,'wait',wait)
    with patch('apps.messaging.management.commands.run_whatsapp_worker.threading.Event',return_value=stop),\
         patch('apps.messaging.management.commands.run_whatsapp_worker.signal.signal'),\
         patch('apps.messaging.management.commands.run_whatsapp_worker.close_old_connections'),\
         patch('apps.messaging.management.commands.run_whatsapp_worker.process_inbox_work',side_effect=[RuntimeError('private token'),0]) as work,\
         patch('apps.messaging.management.commands.run_whatsapp_worker.scheduled_maintenance'),\
         patch('apps.messaging.management.commands.run_whatsapp_worker.pulse_worker') as pulse:
        Command().handle(once=False)
    assert work.call_count==2 and pulse.call_count==1 and waits==[2,3]


def test_maintenance_preserves_offline_message_delivery(kitchens,settings):
    from apps.operations.services import scheduled_maintenance
    settings.ENABLE_TRANSACTIONAL_MESSAGES=False
    with patch('apps.operations.services.run_daily_handoff') as daily,patch('apps.operations.services.send_due_messages') as send:
        scheduled_maintenance()
    daily.assert_called_once();send.assert_not_called()
