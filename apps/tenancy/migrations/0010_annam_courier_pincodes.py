"""Add the six courier pincodes explicitly approved by Annam's administrator."""
from django.db import migrations


PINCODES = ['600005', '600004', '600014', '600017', '600028', '600020']


def add_annam_pincodes(apps, schema_editor):
    Config = apps.get_model('tenancy', 'TenantConfig')
    configs = Config.objects.using(schema_editor.connection.alias).select_for_update().filter(tenant__slug='annam')
    for config in configs:
        settings = dict(config.checkout_settings or {})
        settings['courier_pincodes'] = sorted(set(settings.get('courier_pincodes', []) + PINCODES))
        config.checkout_settings = settings
        config.save(using=schema_editor.connection.alias, update_fields=['checkout_settings'])


class Migration(migrations.Migration):
    dependencies = [('tenancy', '0009_tenantconfig_checkout_settings')]
    operations = [migrations.RunPython(add_annam_pincodes, migrations.RunPython.noop)]
