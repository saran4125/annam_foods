"""Deliver queued WhatsApp messages. Run from the task queue, or on a timer.

    ./manage.py send_pending_messages
"""
from django.core.management.base import BaseCommand

from apps.messaging.services import dispatch_pending


class Command(BaseCommand):
    help = "Deliver queued outbound messages across every tenant."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **opts):
        counts = dispatch_pending(limit=opts["limit"])
        self.stdout.write(self.style.SUCCESS(
            f"sent {counts['sent']} · retrying {counts['failed']} · "
            f"abandoned {counts['abandoned']}"
        ))
