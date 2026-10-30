"""Reviewed snapshots are complete, repeatable, tenant-scoped, and preserve old sales."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from apps.catalog.models import MenuItem, MenuCategory, MenuDay, MenuSchedule, Slot, CatalogSyncRun
from apps.catalog.sync import SnapshotSync, sync_catalog, MANIFEST, audit_catalog_snapshot
from apps.catalog.services import search_shop, resolve_menu
from apps.content.models import Banner
from apps.orders.models import Customer,Order
from apps.tenancy.models import Tenant,TenantConfig
from apps.tenancy.context import tenant_context


@pytest.fixture
def source_catalog(db):
    tenant=Tenant.objects.create(slug='annam',name='Annam Foods',status='active')
    export=json.loads((settings.BASE_DIR/'deploy/annam_seed.json').read_text())
    with tenant_context(tenant):
        TenantConfig.objects.get_or_create(tenant=tenant)
        categories={}
        for row in export['categories']:
            categories[row['slug']]=MenuCategory.objects.create(name=row['name'],slug=row['slug'])
        for row in export['categories']:
            parent=next((c for c in export['categories'] if c['source_id']==row['parent_id']),None)
            if parent:
                category=categories[row['slug']];category.parent=categories[parent['slug']];category.save()
        for row in export['products']:
            if row.get('variants') or not row.get('price') or Decimal(row['price'])<=0:continue
            refs=[r for r in row.get('categories',[]) if r in categories]
            cat=next((categories[r] for r in refs if categories[r].parent_id),categories[refs[0]] if refs else None)
            MenuItem.objects.create(name=row['name'][:120],retailer_id=row['source_id'],price=row['price'],
                fulfilment='courier' if row['fulfilment']=='packaged_goods' else 'scheduled',
                active=row['available'],category=cat)
        for key in ['breakfast','lunch','dinner','snacks']:
            Slot.objects.create(key=key,label=key.title(),order_cutoff='23:59:59')
        yield tenant


def run_sync(apply=True):
    with patch('apps.catalog.sync.timezone.localdate',return_value=date(2026,10,30)):
        return sync_catalog(apply=apply)


def test_snapshot_preview_rolls_back_and_apply_reuses_products_and_matches_required_stock(source_catalog):
    before=MenuItem.objects.count();categories=MenuCategory.objects.count()
    result=run_sync(False)
    assert not result['applied'] and MenuItem.objects.count()==before and MenuCategory.objects.count()==categories
    assert not CatalogSyncRun.objects.exists() and not MenuDay.objects.exists()
    old=MenuItem.objects.get(retailer_id='MG1')
    customer=Customer.objects.create(phone='9999999999',name='Prior customer')
    order=Order.objects.create(order_no='OLD-1',customer=customer,channel='manual',items=[{'name':old.name,'unit_price':'150'}],subtotal=150,total=150,address={'line1':'Old address'})
    result=run_sync();data=json.loads(MANIFEST.read_text());finder=SnapshotSync(data)
    assert result['applied'] and CatalogSyncRun.objects.count()==1
    assert audit_catalog_snapshot()['differences']==[]
    assert MenuItem.objects.filter(retailer_id='MG1').get().pk==old.pk
    for row in data['in_stock']+data['diwali']:
        item=finder.find(row['name']);assert item and item.active and item.in_stock and item.price==Decimal(row['price'])
        assert search_shop().filter(pk=item.pk).exists()
    for row in data['sold_out']:
        item=finder.find(row['name']);assert item and not item.in_stock
        assert not search_shop().filter(pk=item.pk).exists()
    for name in data['stock_off']:assert not finder.find(name).in_stock
    assert finder.find('Mavadu Karam').price==Decimal('280')
    assert 'verify pack size' in finder.find('Mavadu Karam').admin_notes
    assert finder.find('Mango Ginger Pickle').price==Decimal('160')
    assert finder.find('Madras Mixture').weight=='' and 'Needs photo and weight' in finder.find('Madras Mixture').admin_notes
    assert 'Build only' in finder.find('Tomato Vathal').admin_notes
    assert Banner.objects.get(title__icontains='diwali').link=='/shop/diwali-2026/'
    assert search_shop(category=MenuCategory.objects.get(slug='diwali-2026')).count()==29
    for key,count in [('breakfast',11),('lunch',7),('dinner',7)]:
        slot=Slot.objects.get(key=key)
        assert len(resolve_menu(date(2026,10,31),slot))==count
        assert not MenuSchedule.objects.filter(slot=slot,mode='weekday').exists()
    order.refresh_from_db();assert order.total==150 and order.items[0]['unit_price']=='150' and order.address=={'line1':'Old address'}
    changed=finder.find('Madras Mixture');changed.price=321;changed.in_stock=False;changed.save()
    again=run_sync();assert again['already_applied']
    changed.refresh_from_db();assert changed.price==321 and not changed.in_stock


def test_existing_staff_menu_is_preserved_and_past_dates_are_not_written(source_catalog):
    slot=Slot.objects.get(key='lunch');plan=MenuDay.objects.create(slot=slot,on_date=date(2026,10,31),revision=2)
    result=run_sync()
    plan.refresh_from_db();assert plan.revision==2
    assert any('existing staff-saved menu preserved' in note for note in result['report']['review'])


def test_ambiguous_shop_match_rolls_back_entire_patch(source_catalog):
    MenuItem.objects.create(name='Mango Ginger Pickle',fulfilment='courier',price=150)
    count=MenuItem.objects.count()
    with pytest.raises(ValidationError,match='Ambiguous product'):run_sync()
    assert MenuItem.objects.count()==count and not CatalogSyncRun.objects.exists()


def test_snapshot_cannot_be_applied_to_a_different_store_or_changed_after_apply(source_catalog,tmp_path):
    rival=Tenant.objects.create(slug='rival',name='Rival')
    with tenant_context(rival),pytest.raises(ValidationError,match='configured store'):run_sync()
    run_sync()
    data=json.loads(MANIFEST.read_text());data['source']='Changed source'
    changed=tmp_path/'changed.json';changed.write_text(json.dumps(data))
    with pytest.raises(ValidationError,match='cannot be changed'):sync_catalog(apply=True,path=changed)


def test_past_snapshot_menu_never_rewrites_history(source_catalog):
    with patch('apps.catalog.sync.timezone.localdate',return_value=date(2026,11,1)):
        result=sync_catalog(apply=True)
    assert not MenuDay.objects.exists()
    assert any('in the past' in note for note in result['report']['review'])
