import csv
import importlib
import io
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from apps.catalog.models import Slot
from apps.delivery.imports import HEADER, read_meal_zone_csv
from apps.delivery.models import DeliveryZone
from apps.delivery.services import zones_for_pincode
from apps.owner.forms import ZoneForm
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

MIGRATION = 'apps.delivery.migrations.0002_annam_approved_meal_zones'
SOURCE = Path(__file__).resolve().parents[3] / 'deploy' / 'annam_meal_delivery_zones.csv'


def apply_import():
    historical = MigrationLoader(connection).project_state([
        ('delivery', '0002_annam_approved_meal_zones')]).apps
    importlib.import_module(MIGRATION).import_approved_meal_zones(historical, SimpleNamespace(connection=connection))


@pytest.fixture
def imported(db):
    store = Tenant.objects.create(slug='annam', name='Annam Foods')
    other = Tenant.objects.create(slug='rival', name='Other')
    config = store.config
    config.checkout_settings = {'courier_enabled': True, 'courier_pincodes': ['641001'],
                                'courier_fee': '55', 'courier_minimum': '200'}
    config.save()
    with tenant_context(store):
        existing = DeliveryZone.objects.create(pincode='600005', area_name='Triplicane',
                                              delivery_fee='99', min_order='999')
        retired = DeliveryZone.objects.create(pincode='600999', area_name='Old area', delivery_fee='20')
        old_generic = DeliveryZone.objects.create(pincode='600083', area_name='Old generic area')
    with tenant_context(other):
        rival_zone = DeliveryZone.objects.create(pincode='600005', area_name='Other area', delivery_fee='77')
    apply_import()
    return store, other, existing, retired, old_generic, rival_zone


def test_source_contains_all_exported_meal_flags_and_matches_frozen_deployment_data():
    with SOURCE.open(encoding='utf-8-sig', newline='') as source:
        rows = read_meal_zone_csv(source)
    assert len(rows) == 63 and len({row['pincode'] for row in rows}) == 61
    assert {key: sum(key in row['slot_keys'] for row in rows) for key in
            ('breakfast', 'lunch', 'dinner', 'snacks')} == {
                'breakfast': 12, 'lunch': 63, 'dinner': 38, 'snacks': 63}
    frozen = importlib.import_module(MIGRATION).ZONES
    assert [(row['pincode'], row['area_name'], tuple(row['slot_keys']), str(row['delivery_fee']),
             str(row['min_order']), row['active']) for row in rows] == frozen


def test_meal_import_replaces_fees_and_minimums_but_preserves_zone_identity(imported):
    store, _, existing, retired, old_generic, _ = imported
    existing.refresh_from_db()
    assert existing.area_name == 'Triplicane'
    assert existing.delivery_fee == Decimal('10') and existing.min_order == Decimal('100')
    assert existing.slot_keys == ['breakfast', 'lunch', 'dinner', 'snacks']
    retired.refresh_from_db()
    old_generic.refresh_from_db()
    assert not retired.active and not old_generic.active
    with tenant_context(store):
        assert DeliveryZone.objects.filter(active=True).count() == 63
        assert zones_for_pincode('600999', 'lunch') == []
        assert DeliveryZone.objects.filter(pk=retired.pk).exists()
        assert zones_for_pincode('600086', 'breakfast')[0].min_order == Decimal('30')


def test_meal_import_enforces_breakfast_and_dinner_restrictions(imported):
    store = imported[0]
    with tenant_context(store):
        assert zones_for_pincode('600011', 'lunch')[0].delivery_fee == Decimal('100')
        assert zones_for_pincode('600011', 'lunch')[0].min_order == Decimal('320')
        assert zones_for_pincode('600011', 'breakfast') == []
        assert zones_for_pincode('600011', 'dinner') == []
        assert zones_for_pincode('600020', 'breakfast') == []
        assert zones_for_pincode('600020', 'dinner')[0].delivery_fee == Decimal('40')
        assert zones_for_pincode('600011', 'snacks')


def test_shared_pincodes_keep_separate_areas_and_delivery_charges(imported):
    with tenant_context(imported[0]):
        assert {z.area_name: z.delivery_fee for z in zones_for_pincode('600083', 'lunch')} == {
            'Ashok Nagar': Decimal('40'), 'Jaffar Khan Pet': Decimal('60')}
        assert {z.area_name: z.delivery_fee for z in zones_for_pincode('600100', 'lunch')} == {
            'Medavakkam': Decimal('60'), 'Perumbakalm': Decimal('100')}
        assert zones_for_pincode('600100', 'dinner') == []


def test_import_is_repeatable_without_touching_courier_settings_or_another_store(imported):
    store, _, _, _, _, rival_zone = imported
    before = dict(store.config.checkout_settings)
    with tenant_context(store):
        ids = list(DeliveryZone.objects.filter(active=True).values_list('pk', flat=True))
    apply_import()
    with tenant_context(store):
        assert list(DeliveryZone.objects.filter(active=True).values_list('pk', flat=True)) == ids
    store.config.refresh_from_db()
    assert store.config.checkout_settings == before
    rival_zone.refresh_from_db()
    assert rival_zone.active and rival_zone.delivery_fee == Decimal('77')


def test_admin_edit_keeps_imported_snacks_flag_without_creating_a_snacks_menu(imported):
    with tenant_context(imported[0]):
        Slot.objects.create(key='lunch', label='Lunch', order_cutoff='10:30')
        zone = zones_for_pincode('600011', 'lunch')[0]
        form = ZoneForm({'pincode': zone.pincode, 'area_name': zone.area_name,
                         'delivery_fee': '100', 'min_order': '320',
                         'slot_keys': ['lunch', 'snacks'], 'active': 'on'}, instance=zone)
        assert form.is_valid(), form.errors
        assert form.save().slot_keys == ['lunch', 'snacks']
        assert not Slot.objects.filter(key='snacks').exists()


def csv_text(row):
    result = io.StringIO()
    result.write('Export title\n\n')
    writer = csv.writer(result)
    writer.writerow(HEADER)
    writer.writerow(row)
    return result.getvalue()


@pytest.mark.parametrize('column,value', [
    (0, '60000'), (0, 'abcdef'), (2, 'Maybe'), (6, '-10'), (6, 'NaN'),
    (6, 'Infinity'), (6, '10.123'), (8, 'unknown'),
])
def test_invalid_import_values_are_rejected_before_database_changes(column, value):
    row = ['600005', '—', 'Yes', 'Yes', 'Yes', 'Yes', '₹10', '₹100', 'Yes']
    row[column] = value
    with pytest.raises(ValidationError):
        read_meal_zone_csv(io.StringIO(csv_text(row)))


def test_active_zone_with_no_meals_is_rejected_instead_of_becoming_all_meals():
    row = ['600005', '—', 'No', 'No', 'No', 'No', '₹10', '₹100', 'Yes']
    with pytest.raises(ValidationError):
        read_meal_zone_csv(io.StringIO(csv_text(row)))
