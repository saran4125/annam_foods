"""Review or apply the owner-supplied 30 October catalog correction."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from apps.catalog.sync import sync_catalog
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help='Preview the reviewed Annam catalog patch; --apply writes it once per store.'

    def add_arguments(self,parser):
        parser.add_argument('--tenant',default='annam')
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--if-provisioned',action='store_true')

    def handle(self,*args,**options):
        tenant=Tenant.objects.filter(slug=options['tenant']).first()
        if not tenant:
            if options['if_provisioned']:
                self.stdout.write('Catalog sync will run after initial provisioning.')
                return
            raise CommandError('Annam must be provisioned before catalog sync.')
        try:
            with tenant_context(tenant):result=sync_catalog(apply=options['apply'])
        except (ValidationError,ValueError) as exc:raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result,indent=2,ensure_ascii=False))
