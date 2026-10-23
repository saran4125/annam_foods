"""Apply Annam's approved 63-row meal delivery export from 22 October 2026.

Rows are frozen here so later CSV/admin changes cannot alter this migration.
Shop courier coverage and historical order snapshots are not modified.
"""
from django.db import migrations

ZONES = [
    ('600002', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600004', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600005', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '10', '100', True),
    ('600006', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600008', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600010', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600011', '', ('lunch', 'snacks'), '100', '320', True),
    ('600012', '', ('lunch', 'snacks'), '100', '320', True),
    ('600014', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600015', '', ('lunch', 'dinner', 'snacks'), '50', '160', True),
    ('600017', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600018', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600020', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600022', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600024', '', ('lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600025', '', ('lunch', 'snacks'), '40', '160', True),
    ('600026', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600028', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600029', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600030', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600031', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600032', '', ('lunch', 'snacks'), '100', '320', True),
    ('600033', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600034', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '100', True),
    ('600035', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600036', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600040', '', ('lunch', 'snacks'), '60', '160', True),
    ('600041', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600042', '', ('lunch', 'dinner', 'snacks'), '40', '160', True),
    ('600050', '', ('lunch', 'snacks'), '100', '320', True),
    ('600061', '', ('lunch', 'snacks'), '60', '320', True),
    ('600076', '', ('lunch', 'snacks'), '100', '320', True),
    ('600078', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600080', '', ('lunch', 'snacks'), '100', '320', True),
    ('600082', '', ('lunch', 'snacks'), '100', '320', True),
    ('600083', 'Ashok Nagar', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600083', 'Jaffar Khan Pet', ('lunch', 'dinner', 'snacks'), '60', '100', True),
    ('600084', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600085', '', ('lunch', 'dinner', 'snacks'), '40', '160', True),
    ('600086', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '30', '30', True),
    ('600087', '', ('lunch', 'dinner', 'snacks'), '50', '160', True),
    ('600088', '', ('lunch', 'snacks'), '40', '160', True),
    ('600090', '', ('lunch', 'dinner', 'snacks'), '40', '100', True),
    ('600091', '', ('lunch', 'snacks'), '40', '160', True),
    ('600092', '', ('lunch', 'dinner', 'snacks'), '40', '160', True),
    ('600093', '', ('lunch', 'dinner', 'snacks'), '40', '160', True),
    ('600094', '', ('breakfast', 'lunch', 'dinner', 'snacks'), '40', '160', True),
    ('600095', '', ('lunch', 'snacks'), '60', '160', True),
    ('600096', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600097', '', ('lunch', 'snacks'), '100', '320', True),
    ('600099', '', ('lunch', 'snacks'), '100', '320', True),
    ('600100', 'Medavakkam', ('lunch', 'snacks'), '60', '320', True),
    ('600100', 'Perumbakalm', ('lunch', 'snacks'), '100', '320', True),
    ('600101', '', ('lunch', 'snacks'), '60', '160', True),
    ('600102', '', ('lunch', 'snacks'), '60', '160', True),
    ('600106', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600107', '', ('lunch', 'snacks'), '60', '160', True),
    ('600113', '', ('lunch', 'dinner', 'snacks'), '60', '160', True),
    ('600116', '', ('lunch', 'snacks'), '100', '320', True),
    ('600117', '', ('lunch', 'snacks'), '60', '320', True),
    ('600119', '', ('lunch', 'snacks'), '100', '320', True),
    ('600125', '', ('lunch', 'snacks'), '100', '320', True),
    ('600129', '', ('lunch', 'snacks'), '60', '320', True),
]


def import_approved_meal_zones(apps, schema_editor):
    Tenant = apps.get_model('tenancy', 'Tenant')
    Zone = apps.get_model('delivery', 'DeliveryZone')
    alias = schema_editor.connection.alias
    store = Tenant.objects.using(alias).select_for_update().filter(slug='annam').first()
    if store is None:
        return
    zones = Zone.objects.using(alias).filter(tenant_id=store.pk)
    retained = []
    for pin, area, slots, fee, minimum, active in ZONES:
        matching = zones.filter(pincode=pin)
        if area:
            zone = matching.filter(area_name__iexact=area).first()
        else:
            zone = matching.filter(area_name='Delivery area').first()
            if zone is None and matching.count() == 1:
                zone = matching.first()  # Preserve an existing useful area name and ID.
        if zone is None:
            zone = Zone(tenant_id=store.pk, pincode=pin, area_name=area or 'Delivery area')
        elif area:
            zone.area_name = area
        zone.delivery_fee = fee
        zone.min_order = minimum
        zone.slot_keys = list(slots)
        zone.active = active
        zone.save(using=alias)
        retained.append(zone.pk)
    # Retain records for history, but stop accepting orders outside the approved list.
    zones.exclude(pk__in=retained).update(active=False)


class Migration(migrations.Migration):
    dependencies = [('delivery', '0001_initial'), ('tenancy', '0011_annam_bill_logo')]
    operations = [migrations.RunPython(import_approved_meal_zones, migrations.RunPython.noop)]
