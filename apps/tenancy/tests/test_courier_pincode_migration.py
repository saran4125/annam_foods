import importlib
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader


@pytest.mark.django_db
def test_approved_pincodes_preserve_existing_coverage_and_settings_for_annam_only():
    historical = MigrationLoader(connection).project_state([
        ('tenancy', '0009_tenantconfig_checkout_settings')]).apps
    Tenant = historical.get_model('tenancy', 'Tenant')
    Config = historical.get_model('tenancy', 'TenantConfig')
    annam = Tenant.objects.create(slug='annam', name='Annam Foods')
    other = Tenant.objects.create(slug='other', name='Other')
    settings = {'courier_pincodes': ['641001', '600005'], 'courier_enabled': False,
                'courier_fee': '55', 'courier_minimum': '300',
                'closed_dates': ['2026-11-01'], 'payment_instructions': 'Contact Annam.'}
    config = Config.objects.create(tenant=annam, checkout_settings=settings)
    other_config = Config.objects.create(tenant=other, checkout_settings={'courier_pincodes': ['625001']})
    migration = importlib.import_module('apps.tenancy.migrations.0010_annam_courier_pincodes')
    for _ in range(2):
        migration.add_annam_pincodes(historical, SimpleNamespace(connection=connection))
    config.refresh_from_db()
    assert config.checkout_settings == {**settings, 'courier_pincodes': [
        '600004', '600005', '600014', '600017', '600020', '600028', '641001']}
    other_config.refresh_from_db()
    assert other_config.checkout_settings == {'courier_pincodes': ['625001']}
