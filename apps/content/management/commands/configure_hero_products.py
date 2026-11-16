"""Save the owner's chosen homepage product photos without changing the catalog."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.tenancy.models import Tenant, TenantConfig


class Command(BaseCommand):
    help = 'Configure the reviewed podi homepage photos once, preserving other store settings.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=getattr(settings, 'STORE_SLUG', '') or 'annam')
        parser.add_argument('--if-provisioned', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads((Path(settings.BASE_DIR) / 'deploy/annam_hero_products.json').read_text())
        if options['tenant'] != data['tenant_slug']:
            raise CommandError('This photo selection belongs to a different store.')
        tenant = Tenant.objects.filter(slug=options['tenant']).first()
        if tenant is None:
            if options['if_provisioned']:
                self.stdout.write('Hero photo selection waits for store provisioning.')
                return
            raise CommandError('Provision the store first.')
        config = TenantConfig.objects.select_for_update().get(tenant=tenant)
        theme = dict(config.theme or {})
        if theme.get('hero_products_version') == data['version']:
            self.stdout.write('Hero photo selection already configured.')
            return
        theme.update(hero_product_ids=data['retailer_ids'], hero_products_version=data['version'])
        config.theme = theme
        config.save(update_fields=['theme'])
        self.stdout.write('Configured podi and food photos for the homepage hero.')
