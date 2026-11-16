"""Compare the reviewed PHP snapshot and insert missing public store records."""
import json
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


TABLES = {
    'catalog_slot': ('catalog.Slot', ('key',)),
    'catalog_menucategory': ('catalog.MenuCategory', ('slug',)),
    'catalog_menuitem': ('catalog.MenuItem', ('retailer_id',)),
    'catalog_menuday': ('catalog.MenuDay', ('slot_id', 'on_date')),
    'catalog_menuschedule': ('catalog.MenuSchedule', ('item_id', 'slot_id', 'mode', 'on_date', 'weekday')),
    'content_banner': ('content.Banner', ('title',)),
    'content_page': ('content.Page', ('slug',)),
    'delivery_deliveryzone': ('delivery.DeliveryZone', ('pincode', 'area_name')),
}


class Command(BaseCommand):
    help = 'Preview missing PHP public data; --apply inserts only, preserving existing records.'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', default='annam')
        parser.add_argument('--apply', action='store_true')

    def handle(self, *args, **options):
        snapshot = json.loads((Path(settings.BASE_DIR) / 'deploy/annam_php_public_snapshot.json').read_text())
        try:
            with transaction.atomic():
                tenant = Tenant.objects.select_for_update().get(slug=options['tenant'])
                if tenant.slug != snapshot['tenant_slug']:
                    raise CommandError('This snapshot belongs to Annam only.')
                with tenant_context(tenant):
                    report = self.restore(snapshot)
                if not options['apply']:
                    transaction.set_rollback(True)
        except Tenant.DoesNotExist as exc:
            raise CommandError('Provision Annam before comparing the snapshot.') from exc
        report['applied'] = options['apply']
        report['scope'] = 'Public catalog, menus, pages, banners and delivery zones only. Existing rows are unchanged.'
        self.stdout.write(json.dumps(report, indent=2))

    def restore(self, snapshot):
        mappings, report = {}, {}
        self.existing_days = {
            (slot_id, str(on_date))
            for slot_id, on_date in apps.get_model('catalog.MenuDay').objects.values_list('slot_id', 'on_date')
        }
        for table, (label, keys) in TABLES.items():
            model = apps.get_model(label)
            mappings[table] = {}
            report[table] = {'missing': 0, 'existing': 0}
            pending = {row['id']: row for row in snapshot['tables'][table]}
            while pending:
                progressed = False
                for source_id, row in list(pending.items()):
                    values = {}
                    unresolved = False
                    for field in model._meta.concrete_fields:
                        if field.primary_key or field.name == 'tenant' or field.attname not in row:
                            continue
                        value = row[field.attname]
                        if field.is_relation and value is not None:
                            target = field.related_model._meta.db_table
                            if value not in mappings.get(target, {}):
                                unresolved = True
                                break
                            value = mappings[target][value]
                        elif isinstance(field, models.JSONField) and isinstance(value, str):
                            value = json.loads(value)
                        elif isinstance(field, models.BooleanField):
                            value = bool(value)
                        values[field.attname] = value
                    if unresolved:
                        continue
                    lookup = {key: values[key] for key in keys}
                    if any(lookup[key] in ('', None) for key in keys if key in ('retailer_id', 'slug', 'key')):
                        raise CommandError(f'Missing stable identifier in {table}, source ID {source_id}.')
                    matches = list(model.objects.filter(**lookup)[:2])
                    if len(matches) > 1:
                        raise CommandError(f'Ambiguous match in {table}, source ID {source_id}; nothing committed.')
                    if matches:
                        obj = matches[0]
                        report[table]['existing'] += 1
                    else:
                        # Adding rows to a staff-saved date menu would change that menu.
                        if table == 'catalog_menuschedule' and values['mode'] == 'date':
                            if (values['slot_id'], str(values['on_date'])) in self.existing_days:
                                report[table]['preserved_saved_menu'] = report[table].get('preserved_saved_menu', 0) + 1
                                del pending[source_id]
                                progressed = True
                                continue
                        obj = model.objects.create(**values)
                        report[table]['missing'] += 1
                    mappings[table][source_id] = obj.pk
                    del pending[source_id]
                    progressed = True
                if not progressed:
                    raise CommandError(f'Unresolved references in {table}; nothing committed.')
        return report

