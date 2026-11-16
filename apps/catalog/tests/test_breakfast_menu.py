from datetime import date, timedelta
from unittest.mock import patch

from apps.catalog.breakfast_menu import publish_reviewed_breakfast
from apps.catalog.breakfast_review import sync_breakfast
from apps.catalog.models import CatalogSyncRun, MenuDay, MenuItem, MenuSchedule, Slot
from apps.catalog.services import resolve_menu
from apps.catalog.tests.test_snapshot_sync import source_catalog  # noqa: F401
from apps.tenancy.context import tenant_context


DAY = date(2026, 11, 16)


def test_requested_breakfast_appears_today_without_losing_other_dishes_stock_or_other_dates(source_catalog):
    with tenant_context(source_catalog), patch('django.utils.timezone.localdate', return_value=DAY):
        sync_breakfast(source_catalog, apply=True)
        slot = Slot.objects.get(key='breakfast')
        MenuDay.objects.create(slot=slot, on_date=DAY)
        extra = MenuItem.objects.create(name='Existing extra dish', price=99)
        schedule = MenuSchedule.objects.create(item=extra, slot=slot, mode='date', on_date=DAY,
                                               available=True, qty_sold=2, qty_limit=5)
        future = MenuDay.objects.create(slot=slot, on_date=DAY + timedelta(days=1))
        report = publish_reviewed_breakfast(source_catalog)
        assert report['reviewed_dishes'] == 10 and report['total_dishes'] == 11
        assert len(resolve_menu(DAY, slot)) == 9  # Eight in-stock reviewed dishes plus the existing dish.
        assert len(resolve_menu(DAY, slot, include_unavailable=True)) == 11
        schedule.refresh_from_db()
        assert schedule.qty_sold == 2 and schedule.qty_limit == 5
        assert not MenuItem.objects.get(retailer_id='reviewed-breakfast:rava-uppuma').in_stock
        assert MenuItem.objects.filter(name='Rasam Vadai (1)', in_stock=False).exists()
        future.refresh_from_db()
        assert future.revision == 0
        assert not MenuSchedule.objects.filter(slot=slot, on_date=future.on_date).exists()
        # Restarting must not republish dishes after a later staff removal.
        MenuSchedule.objects.filter(slot=slot, on_date=DAY).update(available=False)
        assert publish_reviewed_breakfast(source_catalog)['already_applied']
        assert resolve_menu(DAY, slot) == []


def test_a_later_deployment_does_not_turn_the_reviewed_list_into_a_different_dates_menu(source_catalog):
    with tenant_context(source_catalog), patch('django.utils.timezone.localdate', return_value=DAY + timedelta(days=1)):
        sync_breakfast(source_catalog, apply=True)
        assert 'skipped' in publish_reviewed_breakfast(source_catalog)
        assert not MenuDay.objects.exists()
        assert not CatalogSyncRun.objects.filter(version='owner-breakfast-menu-20261116-v1').exists()
