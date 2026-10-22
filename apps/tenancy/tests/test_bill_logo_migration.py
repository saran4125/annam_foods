import importlib
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader


@pytest.mark.django_db
def test_bill_logo_setup_preserves_website_branding_and_other_stores():
    historical = MigrationLoader(connection).project_state([('tenancy', '0010_annam_courier_pincodes')]).apps
    Tenant = historical.get_model('tenancy', 'Tenant')
    Config = historical.get_model('tenancy', 'TenantConfig')
    annam = Tenant.objects.create(slug='annam', name='Annam Foods')
    other = Tenant.objects.create(slug='other', name='Other')
    original = {'logo_url': '/media/original.png', 'brand': '#FF8507'}
    config = Config.objects.create(tenant=annam, theme=original)
    other_config = Config.objects.create(tenant=other, theme=original)
    migration = importlib.import_module('apps.tenancy.migrations.0011_annam_bill_logo')
    migration.configure_bill_logo(historical, SimpleNamespace(connection=connection))
    config.refresh_from_db()
    assert config.theme == {**original, 'billing_logo_url': '/static/branding/annam-bill-logo.png'}
    other_config.refresh_from_db()
    assert other_config.theme == original
    config.theme['billing_logo_url'] = '/media/custom-bill-logo.png'
    config.save()
    migration.configure_bill_logo(historical, SimpleNamespace(connection=connection))
    config.refresh_from_db()
    assert config.theme['billing_logo_url'] == '/media/custom-bill-logo.png'
