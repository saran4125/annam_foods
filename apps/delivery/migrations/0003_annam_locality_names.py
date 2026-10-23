"""Fill only missing Annam area labels; preserve approved delivery rules."""
from django.db import migrations


LOCALITIES = {
    '600002': 'Anna Road / Chintadripet',
    '600004': 'Mylapore / Mandaveli',
    '600005': 'Tiruvallikkeni / Chepauk',
    '600006': 'Greams Road / Teynampet West',
    '600008': 'Egmore',
    '600010': 'Kilpauk',
    '600011': 'Perambur / Sembiam',
    '600012': 'Puliyanthope / Perambur Barracks',
    '600014': 'Royapettah / Lloyds Estate',
    '600015': 'Saidapet / Guindy North',
    '600017': 'Thygarayanagar (T. Nagar)',
    '600018': 'Teynampet',
    '600020': 'Adyar / Shastri Nagar',
    '600022': 'Rajbhavan',
    '600024': 'Kodambakkam',
    '600025': 'Engineering College (Chennai)',
    '600026': 'Vadapalani',
    '600028': 'Raja Annamalaipuram',
    '600029': 'Aminjikarai',
    '600030': 'Shenoy Nagar',
    '600031': 'Chetput',
    '600032': 'Guindy Industrial Estate / Ekkaduthangal',
    '600033': 'West Mambalam',
    '600034': 'Nungambakkam',
    '600035': 'Nandanam',
    '600036': 'Indian Institute of Technology',
    '600040': 'Anna Nagar',
    '600041': 'Tiruvanmiyur / Palavakkam / Neelankarai',
    '600042': 'Velacheri',
    '600050': 'Padi / Korattur',
    '600061': 'Nanganallur / Pazhavanthangal',
    '600076': 'Korattur RS',
    '600078': 'Kalaignar Karunanidhi Nagar (K. K. Nagar)',
    '600080': 'Korattur / Korattur West',
    '600082': 'Jawahar Nagar / Agaram / G. K. M. Colony',
    '600084': 'Flowers Road',
    '600085': 'Kotturpuram',
    '600086': 'Gopalapuram',
    '600087': 'Valasaravakkam / Alwarthirunagar',
    '600088': 'Adambakkam / Nilamangai Nagar',
    '600090': 'Besantnagar',
    '600091': 'Madipakkam',
    '600092': 'Virugambakkam',
    '600093': 'Saligramam',
    '600094': 'Choolaimedu',
    '600095': 'Maduravoyal / Vanagaram / Ayanambakkam',
    '600096': 'Perungudi',
    '600097': 'Oggiamthoraipakkam / Karapakkam',
    '600099': 'Kolathur / Lakshmipuram',
    '600101': 'Anna Nagar Western Extension',
    '600102': 'Anna Nagar East',
    '600106': 'Arumbakkam',
    '600107': 'Koyambedu / Nerkundram',
    '600113': 'Taramani / Tidel Park',
    '600116': 'Porur / Alapakkam',
    '600117': 'Old Pallavaram / Keelakattalai',
    '600119': 'Sholinganallur',
    '600125': 'Manapakkam / Mugalivakkam',
    '600129': 'Kovilambakkam',
}


def fill_missing_localities(apps, schema_editor):
    Tenant = apps.get_model('tenancy', 'Tenant')
    Zone = apps.get_model('delivery', 'DeliveryZone')
    alias = schema_editor.connection.alias
    store = Tenant.objects.using(alias).select_for_update().filter(slug='annam').first()
    if store is None:
        return
    zones = Zone.objects.using(alias).filter(tenant_id=store.pk)
    for pin, name in LOCALITIES.items():
        # A pre-existing named row may have different delivery rules: never merge it.
        if zones.filter(pincode=pin, area_name__iexact=name).exists():
            continue
        missing = zones.filter(pincode=pin, area_name__in=['', 'Delivery area', '—', '-'])
        # Avoid giving distinct subareas one misleading shared name.
        if missing.count() == 1:
            missing.update(area_name=name)


class Migration(migrations.Migration):
    dependencies = [('delivery', '0002_annam_approved_meal_zones')]
    operations = [migrations.RunPython(fill_missing_localities, migrations.RunPython.noop)]
