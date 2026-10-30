import json
from django.core.management.base import BaseCommand,CommandError
from apps.catalog.sync import audit_catalog_snapshot
from apps.tenancy.models import Tenant
from apps.tenancy.context import tenant_context


class Command(BaseCommand):
    help='Read-only comparison against the reviewed owner snapshot (not a fresh live crawl).'

    def add_arguments(self,parser):parser.add_argument('--tenant',default='annam')

    def handle(self,*args,**options):
        tenant=Tenant.objects.filter(slug=options['tenant']).first()
        if not tenant:raise CommandError('Unknown store.')
        with tenant_context(tenant):result=audit_catalog_snapshot()
        self.stdout.write(json.dumps(result,indent=2,ensure_ascii=False))
        if result['differences']:raise CommandError('Stored catalog differs from the reviewed snapshot. See report above.')
