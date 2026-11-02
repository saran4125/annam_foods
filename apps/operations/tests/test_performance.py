from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.owner.tests.test_owner import kitchens,owner,signed_in,catalog,HOST
from apps.catalog.models import MenuCategory,MenuItem
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig


def test_staff_category_queries_do_not_grow_with_each_category(signed_in,kitchens,catalog):
    with CaptureQueriesContext(connection) as baseline:signed_in.get('/manage/categories/',HTTP_HOST=HOST)
    with tenant_context(kitchens[0]):
        for i in range(20):
            category=MenuCategory.objects.create(name=f'Group {i}',slug=f'group-{i}')
            MenuItem.objects.create(name=f'Product {i}',category=category,price=100,fulfilment='courier')
    with CaptureQueriesContext(connection) as grown:response=signed_in.get('/manage/categories/',HTTP_HOST=HOST)
    assert response.context['total']==21 and len(grown)<=len(baseline)+2


def test_shop_responses_are_bounded_and_pages_preserve_search(signed_in,kitchens,catalog):
    TenantConfig.objects.filter(tenant=kitchens[0]).update(features={'snacks_courier':True})
    with tenant_context(kitchens[0]):
        MenuItem.objects.bulk_create([MenuItem(tenant=kitchens[0],name=f'Podi {i}',category=catalog['cat'],price=100,fulfilment='courier') for i in range(75)])
    response=signed_in.get('/shop/podi/',{'q':'Podi','sort':'name'},HTTP_HOST=HOST)
    assert len(response.context['items'])==36 and response.context['item_total']==76
    assert b'q=Podi' in response.content and b'sort=name' in response.content
    page=signed_in.get('/shop/podi/',{'q':'Podi','sort':'name','page':3},HTTP_HOST=HOST)
    assert len(page.context['items'])==4
