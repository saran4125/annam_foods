"""Owner-approved 600041 split; no fees guessed for other shared pincodes."""
from django.db import migrations


def update_approved_areas(apps,schema_editor):
    Tenant=apps.get_model('tenancy','Tenant');Zone=apps.get_model('delivery','DeliveryZone');Slot=apps.get_model('catalog','Slot')
    for tenant in Tenant.objects.using(schema_editor.connection.alias).filter(slug='annam'):
        Slot.objects.using(schema_editor.connection.alias).get_or_create(tenant_id=tenant.pk,key='snacks',defaults={'label':'Snacks','order_cutoff':'23:59:59','order_opens_at':'00:00','order_days_before':1,'sort':3,'active':True})
        existing=Zone.objects.using(schema_editor.connection.alias).filter(tenant_id=tenant.pk,pincode='600041').first()
        if not existing:
            continue
        keys=existing.slot_keys or ['lunch','dinner','snacks']
        recognized=Zone.objects.using(schema_editor.connection.alias).filter(tenant_id=tenant.pk,pincode='600041',area_name__in=['','Delivery area','Tiruvanmiyur / Palavakkam / Neelankarai'])
        named=Zone.objects.using(schema_editor.connection.alias).filter(tenant_id=tenant.pk,pincode='600041',area_name='Thiruvanmiyur').first()
        if not named and recognized.exists():
            chosen=recognized.first();chosen.area_name='Thiruvanmiyur';chosen.delivery_fee='40.00';chosen.save(using=schema_editor.connection.alias,update_fields=['area_name','delivery_fee'])
            recognized.exclude(pk=chosen.pk).update(active=False)
        elif named:
            recognized.update(active=False)
        for name,fee in [('Thiruvanmiyur','40.00'),('Kottivakkam','60.00')]:
            Zone.objects.using(schema_editor.connection.alias).update_or_create(tenant_id=tenant.pk,pincode='600041',area_name=name,defaults={'delivery_fee':fee,'min_order':existing.min_order,'slot_keys':keys,'active':True})


class Migration(migrations.Migration):
    dependencies=[('delivery','0003_annam_locality_names'),('catalog','0005_slot_order_days_before_slot_order_opens_at')]
    operations=[migrations.RunPython(update_approved_areas,migrations.RunPython.noop)]
