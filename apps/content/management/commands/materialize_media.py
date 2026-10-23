from django.conf import settings
from django.core.management.base import BaseCommand

from apps.content.local_images import localize_store_images
from apps.content.storage import restore_bundled_media
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = 'Copy bundled, legacy editor and configured image sources into the media folder.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default=getattr(settings, 'STORE_SLUG', '') or 'annam')
        parser.add_argument('--download', action='store_true',
                            help='Also import HTTPS images from approved Annam source hosts.')

    def handle(self, *args, **options):
        count = restore_bundled_media()
        tenant = Tenant.objects.filter(slug=options['tenant']).first()
        failures = localize_store_images(tenant, download=options['download']) if tenant else []
        self.stdout.write(f'Media recovery: {count} bundled files copied; {len(failures)} unresolved image links.')
        for url, reason in failures:
            # Do not print query strings, which may contain signed URL credentials.
            self.stderr.write(f'Unchanged image: {url.split("?")[0]} ({reason})')
