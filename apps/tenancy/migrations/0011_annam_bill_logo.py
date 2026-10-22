"""Use the administrator-supplied Annam bill logo without changing the storefront."""
from django.db import migrations


def configure_bill_logo(apps, schema_editor):
    Config = apps.get_model('tenancy', 'TenantConfig')
    for config in Config.objects.using(schema_editor.connection.alias).select_for_update().filter(tenant__slug='annam'):
        theme = dict(config.theme or {})
        theme.setdefault('billing_logo_url', '/static/branding/annam-bill-logo.png')
        config.theme = theme
        config.save(using=schema_editor.connection.alias, update_fields=['theme'])


class Migration(migrations.Migration):
    dependencies = [('tenancy', '0010_annam_courier_pincodes')]
    operations = [migrations.RunPython(configure_bill_logo, migrations.RunPython.noop)]
