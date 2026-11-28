"""Menu membership controls visibility; stock controls ordering, on every date."""
from datetime import timedelta
import re
import pytest
from apps.catalog.models import MenuItem, MenuSchedule
from apps.catalog.services import published_menu, resolve_menu
from apps.catalog.inventory import configure
from apps.orders.services import price_lines, RequestedLine, ItemNotOnMenu
from apps.tenancy.context import tenant_context
from .test_storefront import kitchen, menu, HOST


@pytest.mark.parametrize('days',[0,1])
@pytest.mark.parametrize('reason',['manual','quantity','legacy_limit'])
def test_published_sold_out_dish_stays_visible_but_cannot_be_ordered(client,kitchen,menu,days,reason):
    day=menu['date']+timedelta(days=days);slot=menu['slot'];item=menu['item']
    with tenant_context(kitchen):
        row,_=MenuSchedule.objects.get_or_create(item=item,slot=slot,mode='date',on_date=day)
        if reason=='manual':
            item.in_stock=False;item.save(update_fields=['in_stock'])
        elif reason=='quantity':configure(item,on_date=day,slot=slot,tracked=True,quantity=0)
        else:row.qty_limit=2;row.qty_sold=2;row.save()
        assert resolve_menu(day,slot)==[]
        shown=published_menu(day,slot)
        assert [e.item.pk for e in shown]==[item.pk] and shown[0].sold_out
        with pytest.raises(ItemNotOnMenu):price_lines([RequestedLine(item.pk,1)],delivery_date=day,slot=slot)
    page=client.get('/menu/',{'date':str(day),'slot':slot.key},HTTP_HOST=HOST)
    assert page.status_code==200
    card=re.search(r'<li class="dish" data-item="'+str(item.pk)+r'">(.*?)</li>',page.content.decode(),re.S).group(1)
    assert 'Out of stock' in card and 'data-cart-form' not in card
    if days==0:
        home=client.get('/',HTTP_HOST=HOST)
        assert home.status_code==200 and b'Out of stock' in home.content
        assert home.context['highlights'][0]['entries'][0].item.pk==item.pk


@pytest.mark.parametrize('days',[0,1])
def test_removed_or_archived_dishes_are_hidden_even_when_out_of_stock(client,kitchen,menu,days):
    day=menu['date']+timedelta(days=days);slot=menu['slot']
    with tenant_context(kitchen):
        for name,available,active in [('Removed fixture',False,True),('Archived fixture',True,False)]:
            item=MenuItem.objects.create(name=name,price=100,in_stock=False,active=active)
            MenuSchedule.objects.create(item=item,slot=slot,mode='date',on_date=day,available=available)
        names=[e.item.name for e in published_menu(day,slot)]
        assert 'Removed fixture' not in names and 'Archived fixture' not in names
    page=client.get('/menu/',{'date':str(day),'slot':slot.key},HTTP_HOST=HOST)
    assert b'Removed fixture' not in page.content and b'Archived fixture' not in page.content
