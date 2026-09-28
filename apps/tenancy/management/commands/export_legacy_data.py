"""Private local SQLite export; all-tenant scope is explicit and short-lived."""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from apps.tenancy.context import all_tenants


class Command(BaseCommand):
    help = "Export a migrated, disposable legacy SQLite copy for PostgreSQL import."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        if connection.vendor != "sqlite" or settings.SETTINGS_MODULE != "config.settings.legacy_sqlite":
            raise CommandError("Use the isolated legacy SQLite settings and a copied database.")
        with all_tenants():
            call_command("dumpdata", "--natural-foreign", "--natural-primary",
                         "--exclude", "contenttypes", "--exclude", "auth.permission",
                         "--exclude", "admin.logentry", "--exclude", "sessions",
                         output=options["output"], verbosity=0)
