import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.meal_categories import normalize_meal_categories
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = 'Group weekday-labelled dishes under Breakfast, Lunch, Dinner or Snacks; keep schedules unchanged.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=getattr(settings, 'STORE_SLUG', '') or 'annam')
        parser.add_argument('--if-provisioned', action='store_true')

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options['tenant']).first()
        if tenant is None:
            if options['if_provisioned']:
                self.stdout.write('Meal categories will be grouped after provisioning.')
                return
            raise CommandError('Provision the store first.')
        try:
            report = normalize_meal_categories(tenant)
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report))
