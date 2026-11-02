"""Process durable inbox replies and Meta-to-n8n forwarding without Redis."""
import logging
import time
import signal
import threading
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from apps.messaging.worker import process_inbox_work
from apps.operations.health import pulse_worker
from apps.operations.services import scheduled_maintenance

log=logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the database-backed WhatsApp inbox worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if options["once"]:
            count=process_inbox_work()
            pulse_worker()
            self.stdout.write(f"Processed {count} inbox tasks.")
            return
        stop = threading.Event()
        failures=0
        last_pulse=0
        last_maintenance=0
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.is_set():
            close_old_connections()
            try:
                process_inbox_work()
                now=time.monotonic()
                if now-last_maintenance>=60:
                    scheduled_maintenance()
                    last_maintenance=now
                if now-last_pulse>=15:
                    pulse_worker()
                    last_pulse=now
                failures=0
            except Exception as exc:
                failures+=1
                # No customer payloads, tokens or provider error bodies in logs.
                log.error('Inbox worker iteration failed: %s',type(exc).__name__)
            stop.wait(min(30,2**min(failures,5)) if failures else 3)
        close_old_connections()
