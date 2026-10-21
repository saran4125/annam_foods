from django.db import migrations


def preserve_credentials(apps, schema_editor):
    Secrets = apps.get_model('tenancy', 'TenantSecrets')
    Connection = apps.get_model('payments', 'RazorpayConnection')
    for row in Secrets.objects.exclude(razorpay_key_id='').iterator():
        mode = 'live' if row.razorpay_live_mode else 'test'
        Connection.objects.get_or_create(tenant_id=row.tenant_id, mode=mode, defaults={
            'key_id': row.razorpay_key_id, '_key_secret': row._razorpay_secret,
            '_webhook_secret': row._razorpay_webhook_secret, 'enabled': False})


class Migration(migrations.Migration):
    dependencies = [('payments', '0001_initial')]
    operations = [migrations.RunPython(preserve_credentials, migrations.RunPython.noop)]
