import json
from datetime import date

from django.conf import settings

from apps.catalog.breakfast_review import sync_breakfast
from apps.catalog.models import CatalogSyncRun, MenuDay, MenuItem, MenuSchedule, Slot
from apps.catalog.tests.test_snapshot_sync import source_catalog  # noqa: F401
from apps.owner.menu_services import menu_items, menu_selection
from apps.tenancy.context import tenant_context


def test_review_adds_ten_breakfast_products_without_publishing_dates_or_resetting_later_edits(source_catalog):
    with tenant_context(source_catalog):
        before = MenuItem.objects.count()
        assert not sync_breakfast(source_catalog)['applied']
        assert MenuItem.objects.count() == before and not CatalogSyncRun.objects.exists()
        existing = MenuItem.objects.get(retailer_id='SI1')
        photo = existing.image.name
        slot = Slot.objects.get(key='breakfast')
        day = date(2026, 11, 16)
        MenuDay.objects.create(slot=slot, on_date=day)
        sync_breakfast(source_catalog, apply=True)
        source = json.loads((settings.BASE_DIR / 'deploy/annam_breakfast_review_20261116.json').read_text())
        for row in source['items']:
            item = MenuItem.objects.get(retailer_id=row['retailer_id'])
            assert item.name == row['name']
            assert str(item.price) == row['price'] + '.00'
            assert item.in_stock == row['in_stock'] and item.active
            assert item.category.slug == 'breakfast'
        existing.refresh_from_db()
        assert existing.image.name == photo
        assert not MenuSchedule.objects.exists()
        selected = menu_selection({'meal': 'breakfast', 'date': 'all'})
        assert menu_items(selected).count() == 10
        assert not menu_items(menu_selection({'meal': 'breakfast', 'date': day.isoformat()})).exists()
        existing.price = '999.00'
        existing.in_stock = False
        existing.save()
        assert sync_breakfast(source_catalog, apply=True)['already_applied']
        existing.refresh_from_db()
        assert str(existing.price) == '999.00' and not existing.in_stock
