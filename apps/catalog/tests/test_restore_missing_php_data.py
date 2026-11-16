import io
import json
from datetime import date

from django.core.management import call_command

from apps.catalog.models import MenuDay, MenuItem, MenuSchedule, Slot
from apps.catalog.tests.test_snapshot_sync import source_catalog  # noqa: F401
from apps.tenancy.context import tenant_context


def restore(apply=False):
    output = io.StringIO()
    call_command('restore_missing_php_data', apply=apply, stdout=output)
    return json.loads(output.getvalue())


def test_preview_rolls_back_and_apply_preserves_prices_stock_images_and_is_repeatable(source_catalog):
    with tenant_context(source_catalog):
        original = MenuItem.objects.exclude(retailer_id=None).first()
        original.price = '123.45'
        original.in_stock = False
        original.image = 'menu/staff-upload.jpg'
        original.save()
        before = MenuItem.objects.count()
        preview = restore()
        assert preview['catalog_menuitem']['missing'] > 0
        assert MenuItem.objects.count() == before
        result = restore(True)
        assert result['catalog_menuitem'] == preview['catalog_menuitem']
        original.refresh_from_db()
        assert str(original.price) == '123.45'
        assert not original.in_stock
        assert original.image.name == 'menu/staff-upload.jpg'
        assert MenuItem.objects.count() == before + result['catalog_menuitem']['missing']
        second = restore(True)
        assert all(counts['missing'] == 0 for key, counts in second.items() if isinstance(counts, dict))


def test_saved_empty_date_menu_stays_empty(source_catalog):
    with tenant_context(source_catalog):
        from django.conf import settings
        snapshot = json.loads((settings.BASE_DIR / 'deploy/annam_php_public_snapshot.json').read_text())
        source_row = snapshot['tables']['catalog_menuschedule'][0]
        assert source_row['mode'] == 'date'
        source_slot = next(r for r in snapshot['tables']['catalog_slot'] if r['id'] == source_row['slot_id'])
        slot = Slot.objects.get(key=source_slot['key'])
        day = date.fromisoformat(source_row['on_date'])
        MenuDay.objects.create(slot=slot, on_date=day)
        report = restore(True)
        assert report['catalog_menuschedule']['preserved_saved_menu'] > 0
        assert not MenuSchedule.objects.filter(slot=slot, on_date=day).exists()
