import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.breakfast_review import sync_breakfast
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = 'Preview the screenshot-reviewed breakfast catalog; --apply saves it once without adding schedules.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=getattr(settings, 'STORE_SLUG', '') or 'annam')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--if-provisioned', action='store_true')

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options['tenant']).first()
        if not tenant:
            if options['if_provisioned']:
                self.stdout.write('Breakfast review waits for provisioning.')
                return
            raise CommandError('Provision Annam first.')
        try:
            result = sync_breakfast(tenant, apply=options['apply'])
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
