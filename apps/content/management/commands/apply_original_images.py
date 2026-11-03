from django.conf import settings
from django.core.management.base import BaseCommand
from apps.content.public_media import apply_originals
from apps.tenancy.models import Tenant

class Command(BaseCommand):
    help = 'Restore verified public originals and match catalog image fields only.'
    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=getattr(settings, 'STORE_SLUG', '') or 'annam')
    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=options['tenant']).first()
        if not tenant:
            self.stdout.write('Image recovery waits until the store is provisioned.')
            return
        self.stdout.write(str(apply_originals(tenant)))
