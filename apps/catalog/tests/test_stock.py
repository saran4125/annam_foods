"""One stock flag gates storefront, cart pricing, daily meals and staff capture."""
from datetime import date
import pytest
from apps.owner.tests.test_owner import kitchens,owner,signed_in,catalog,HOST,OTHER
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig
from apps.catalog.models import MenuItem,MenuSchedule,Slot
from apps.catalog.services import search_shop,resolve_menu
from apps.orders.services import price_courier_lines,price_lines,RequestedLine,ItemNotOnMenu
from apps.billing.services import create_staff_order,staff_catalog
from apps.billing.forms import OrderLineForm


def test_stock_switch_is_staff_only_scoped_and_separate_from_visibility(signed_in,kitchens,catalog,client):
    item=catalog['dish'];url=f'/manage/dishes/{item.pk}/stock/'
    from django.test import Client
    assert Client().post(url,HTTP_HOST=HOST).status_code==302
    assert signed_in.get(url,HTTP_HOST=HOST).status_code==405
    assert signed_in.post(url,HTTP_HOST=OTHER).status_code==403
    response=signed_in.post(url,{'next':'/manage/categories/'},HTTP_HOST=HOST)
    assert response['Location']=='/manage/categories/'
    item.refresh_from_db();assert not item.in_stock and item.active
    with tenant_context(kitchens[0]):
        assert not search_shop().filter(pk=item.pk).exists()
        with pytest.raises(ItemNotOnMenu):price_courier_lines([RequestedLine(item.pk,1)])
        assert item.pk not in [row['id'] for row in staff_catalog()]
        assert not OrderLineForm({'item':item.pk,'meal':'snacks','quantity':1}).is_valid()
        with pytest.raises(ValueError,match='unavailable'):
            create_staff_order(kitchens[0],name='Buyer',phone='9999999999',channel='manual',payment_mode='manual',
                requested=[(item.pk,1,'snacks')],token='stock-denied',actor='test')
    signed_in.post(url,HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):assert search_shop().filter(pk=item.pk).exists()


def test_sold_out_stock_blocks_a_crafted_cart_add_and_removes_stale_lines(signed_in,kitchens,catalog):
    tenant=kitchens[0];item=catalog['dish']
    TenantConfig.objects.filter(tenant=tenant).update(features={'snacks_courier':True,'website_ordering':True})
    signed_in.post('/cart/add/',{'kind':'shop','item_id':item.pk,'delta':1},HTTP_HOST=HOST)
    item.in_stock=False;item.save(update_fields=['in_stock'])
    signed_in.post('/cart/add/',{'kind':'shop','item_id':item.pk,'delta':1},HTTP_HOST=HOST)
    response=signed_in.get('/cart/',HTTP_HOST=HOST)
    assert b'data-testid="cart-empty"' in response.content
    assert signed_in.get(f'/shop/item/{item.pk}/',HTTP_HOST=HOST).status_code==404
    page=signed_in.get('/shop/',HTTP_HOST=HOST)
    assert item.pk not in [p.pk for p in page.context['items']]


def test_global_stock_respects_date_menu_availability_and_preserves_internal_notes(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        item=MenuItem.objects.create(name='Sold out meal',price=100,in_stock=False,weight='200 gm',admin_notes='Private stock review')
        MenuSchedule.objects.create(item=item,slot=catalog['slot'],mode='date',on_date=date(2026,10,31),available=True)
        assert not resolve_menu(date(2026,10,31),catalog['slot'])
        entry=resolve_menu(date(2026,10,31),catalog['slot'],include_unavailable=True)[0]
        assert entry.sold_out and not entry.is_orderable
        with pytest.raises(ItemNotOnMenu):price_lines([RequestedLine(item.pk,1)],delivery_date=date(2026,10,31),slot=catalog['slot'])
    edit=signed_in.get(f'/manage/dishes/{item.pk}/',HTTP_HOST=HOST)
    assert 'in_stock' in edit.context['form'].fields and 'admin_notes' in edit.context['form'].fields
