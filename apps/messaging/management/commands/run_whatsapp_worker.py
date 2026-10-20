"""Process durable inbox replies and Meta-to-n8n forwarding without Redis."""
import signal
import threading
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from apps.messaging.worker import process_inbox_work


class Command(BaseCommand):
    help = "Run the database-backed WhatsApp inbox worker."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if options["once"]:
            self.stdout.write(f"Processed {process_inbox_work()} inbox tasks.")
            return
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.is_set():
            close_old_connections()
            process_inbox_work()
            stop.wait(3)
        close_old_connections()
