"""Saved display order is consistent across shelves, pages and home picks."""
import pytest
from apps.tenancy.context import tenant_context
from apps.catalog.models import MenuItem, MenuCategory
from apps.catalog.services import search_shop, shop_categories, popular_shop_items
from apps.catalog.library import ensure_defaults
from .test_shop import shop, kitchen, menu, HOST


def test_product_rank_takes_priority_over_its_category_rank(client,shop,kitchen):
    with tenant_context(kitchen):
        first,later=shop['butter'],shop['ellu']
        first.sort=1;first.save(update_fields=['sort']);first.category.sort=90;first.category.save(update_fields=['sort'])
        later.sort=9;later.save(update_fields=['sort']);later.category.sort=0;later.category.save(update_fields=['sort'])
        assert list(search_shop().values_list('pk',flat=True))==[first.pk,later.pk]
    page=client.get('/shop/',HTTP_HOST=HOST)
    assert [p.pk for p in page.context['items']]==[first.pk,later.pk]
    assert b'Display order' in page.content


def test_main_shop_shelf_includes_products_from_every_shop_category(client,shop,kitchen):
    with tenant_context(kitchen):
        ensure_defaults();category=MenuCategory.objects.get(slug='shop')
        assert set(search_shop(category=category).values_list('pk',flat=True))=={shop['butter'].pk,shop['ellu'].pk}
        assert next(c for c in shop_categories() if c.slug=='shop').item_count==2
    page=client.get('/shop/shop/',HTTP_HOST=HOST)
    assert page.status_code==200 and page.context['item_total']==2
    assert {item.pk for item in page.context['items']}=={shop['butter'].pk,shop['ellu'].pk}


@pytest.mark.parametrize('sort',['featured','price','-price','name'])
def test_equal_rank_name_and_price_have_stable_nonoverlapping_pages(client,shop,kitchen,sort):
    with tenant_context(kitchen):
        ids=[MenuItem.objects.create(name='Stable display fixture',price=100,sort=7,fulfilment='courier',category=shop['butter'].category).pk for _ in range(75)]
    found=[]
    for number in (1,2,3):
        page=client.get('/shop/',{'q':'Stable display fixture','sort':sort,'page':number},HTTP_HOST=HOST)
        found += [item.pk for item in page.context['items']]
    assert found==ids and len(set(found))==75


def test_home_favourite_is_not_lost_beyond_first_sixty_products(shop,kitchen):
    with tenant_context(kitchen):
        for n in range(65):MenuItem.objects.create(name=f'Padding {n}',price=100,sort=n,fulfilment='courier')
        late=MenuItem.objects.create(name='Saved home favourite',price=100,sort=1000,fulfilment='courier',tags=['featured'])
        assert late.pk in [item.pk for item in popular_shop_items()]


def test_photos_do_not_override_display_order_inside_home_groups(shop,kitchen):
    with tenant_context(kitchen):
        first=MenuItem.objects.create(name='First without photo',price=100,sort=1,fulfilment='courier')
        later=MenuItem.objects.create(name='Later with photo',price=100,sort=10,fulfilment='courier',image='menu/sort-fixture.jpg')
        chosen=[item.pk for item in popular_shop_items()]
        assert chosen.index(first.pk)<chosen.index(later.pk)
