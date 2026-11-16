import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.breakfast_menu import publish_reviewed_breakfast
from apps.catalog.models import Slot
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = 'Add the owner-reviewed dishes to the explicitly requested breakfast date once.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=getattr(settings, 'STORE_SLUG', '') or 'annam')
        parser.add_argument('--if-provisioned', action='store_true')

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options['tenant']).first()
        if not tenant:
            if options['if_provisioned']:
                self.stdout.write('Breakfast scheduling waits for store provisioning.')
                return
            raise CommandError('Provision the store first.')
        try:
            result = publish_reviewed_breakfast(tenant)
        except (ValidationError, Slot.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result))
