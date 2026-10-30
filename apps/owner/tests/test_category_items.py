"""Category names open scoped catalog controls; hierarchy stays saved, not editable here."""
from urllib.parse import urlencode
import pytest
from apps.owner.tests.test_owner import kitchens, owner, signed_in, catalog, HOST, OTHER
from apps.tenancy.context import tenant_context
from apps.catalog.models import MenuCategory, MenuItem


def items_url(category):
    return f'/manage/categories/{category.pk}/items/'


def product_data(**overrides):
    return {'name':'New Podi','price':'125','fulfilment':'courier','sort':'0','active':'on','description':'',**overrides}


def test_category_name_and_product_count_open_the_item_list(signed_in,catalog):
    response=signed_in.get('/manage/categories/',HTTP_HOST=HOST)
    html=response.content.decode();url=items_url(catalog['cat'])
    assert 'Inside' not in response.context['headers']
    assert response.context['rows'][0]['title_url']==url+'?type=courier&status=1'
    assert html.count(f'href="{url}?type=courier&amp;status=1"')>=2 and '1 on website' in html


def test_category_items_show_both_meals_and_shop_products_not_unrelated_items(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        meal=MenuItem.objects.create(name='Meal in Podi',price=100,category=catalog['cat'],fulfilment='scheduled')
        other=MenuCategory.objects.create(name='Sweets',slug='sweets')
        MenuItem.objects.create(name='Unrelated sweet',price=100,category=other)
    response=signed_in.get(items_url(catalog['cat']),HTTP_HOST=HOST)
    assert {row['obj'].pk for row in response.context['rows']}=={catalog['dish'].pk,meal.pk}
    assert response.context['menu_ui']=={} and response.context['category']==catalog['cat']
    assert 'Category' not in response.context['headers']
    assert b'Unrelated sweet' not in response.content and b'Rival Roll' not in response.content
    assert b'Edit category' in response.content and response.context['add_label']=='Add item'


def test_add_preselects_category_ignores_forged_assignment_and_returns_to_items(signed_in,kitchens,catalog):
    category=catalog['cat'];url=items_url(category)+'new/'
    page=signed_in.get(url,HTTP_HOST=HOST)
    assert page.context['form'].fields['category'].disabled
    assert page.context['form'].initial['category']==category.pk
    with tenant_context(kitchens[0]):other=MenuCategory.objects.create(name='Other',slug='other')
    response=signed_in.post(url,product_data(category=str(other.pk)),HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']==items_url(category)
    with tenant_context(kitchens[0]):assert MenuItem.objects.get(name='New Podi').category_id==category.pk
    response=signed_in.post(url,product_data(name='Another Podi',save_add='1'),HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location'].startswith(url)


def test_edit_toggle_and_delete_preserve_the_category_return_path(signed_in,kitchens,catalog):
    category=catalog['cat'];dish=catalog['dish'];base=items_url(category)+str(dish.pk)+'/'
    return_url=items_url(category)+'?q=Ellu&status=1'
    response=signed_in.post(base+'?'+urlencode({'next':return_url}),product_data(name='Edited Podi'),HTTP_HOST=HOST)
    assert response['Location']==return_url
    response=signed_in.post(base+'toggle/',HTTP_HOST=HOST)
    assert response['Location']==items_url(category)
    with tenant_context(kitchens[0]):assert not MenuItem.objects.get(pk=dish.pk).active
    page=signed_in.get(base+'delete/?'+urlencode({'next':return_url}),HTTP_HOST=HOST)
    assert page.context['edit_url'].startswith(base)
    assert MenuItem.all_tenants.filter(pk=dish.pk).exists()
    response=signed_in.post(base+'delete/',{'next':return_url},HTTP_HOST=HOST)
    assert response['Location']==return_url
    with tenant_context(kitchens[0]):assert not MenuItem.objects.filter(pk=dish.pk).exists()


@pytest.mark.parametrize('action',['','delete/','toggle/'])
def test_item_actions_cannot_target_another_category_or_tenant(signed_in,kitchens,catalog,action):
    with tenant_context(kitchens[0]):
        other=MenuCategory.objects.create(name='Other',slug='other')
        unrelated=MenuItem.objects.create(name='Other item',price=100,category=other)
    for item in [unrelated,catalog['theirs']]:
        url=items_url(catalog['cat'])+str(item.pk)+'/'+action
        response=signed_in.post(url,product_data(),HTTP_HOST=HOST) if action=='toggle/' else signed_in.get(url,HTTP_HOST=HOST)
        assert response.status_code==404
    assert signed_in.get(items_url(catalog['cat']),HTTP_HOST=OTHER).status_code==403


def test_removing_parent_field_preserves_existing_hierarchy_and_ignores_posted_parent(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        parent=MenuCategory.objects.create(name='Parent',slug='parent')
        child=MenuCategory.objects.create(name='Child',slug='child',parent=parent)
    page=signed_in.get(f'/manage/categories/{child.pk}/',HTTP_HOST=HOST)
    assert 'parent' not in page.context['form'].fields and b'Inside category' not in page.content
    response=signed_in.post(f'/manage/categories/{child.pk}/',{'name':'Renamed child','slug':'child','sort':0,'active':'on','parent':child.pk},HTTP_HOST=HOST)
    assert response.status_code==302
    child.refresh_from_db();assert child.parent_id==parent.pk


def test_empty_category_has_add_action_and_search_status_and_pages_stay_scoped(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        empty=MenuCategory.objects.create(name='Empty',slug='empty')
        MenuItem.objects.bulk_create([MenuItem(tenant=kitchens[0],name=f'Podi {i}',price=100,category=catalog['cat'],fulfilment='courier') for i in range(31)])
    page=signed_in.get(items_url(empty),HTTP_HOST=HOST)
    assert b'No items in Empty yet.' in page.content and page.context['new_url'].startswith(items_url(empty)+'new/')
    page=signed_in.get(items_url(catalog['cat']),{'q':'Podi','status':'1'},HTTP_HOST=HOST)
    assert page.context['page'].paginator.count==32
    assert 'q=Podi' in page.context['querystring'] and 'status=1' in page.context['querystring']
    for row in page.context['rows']:
        assert row['edit_url'].startswith(items_url(catalog['cat'])) and row['toggle_url'].startswith(items_url(catalog['cat']))
    page=signed_in.get(items_url(catalog['cat']),{'q':'Podi','status':'1','page':2},HTTP_HOST=HOST)
    assert len(page.context['rows'])==2


def test_parent_category_lists_and_counts_the_same_products_as_the_storefront(signed_in,kitchens,catalog):
    from apps.catalog.services import search_shop
    with tenant_context(kitchens[0]):
        child=MenuCategory.objects.create(name='Kitchen Podis',slug='kitchen-podis',parent=catalog['cat'])
        grandchild=MenuCategory.objects.create(name='Rice Mix',slug='rice-mix',parent=child)
        products=[MenuItem.objects.create(name=f'Child podi {i}',price=100,category=child if i<10 else grandchild,fulfilment='courier') for i in range(20)]
        expected=set(search_shop(category=catalog['cat']).values_list('pk',flat=True))
    page=signed_in.get(items_url(catalog['cat']),HTTP_HOST=HOST)
    assert {row['obj'].pk for row in page.context['rows']}==expected
    listing=signed_in.get('/manage/categories/',HTTP_HOST=HOST)
    shelf=next(row['obj'] for row in listing.context['rows'] if row['obj'].pk==catalog['cat'].pk)
    assert shelf.product_count==shelf.website_count==21
    product=products[0];base=items_url(catalog['cat'])+str(product.pk)+'/'
    response=signed_in.post(base,product_data(name='Updated child podi',category=catalog['cat'].pk),HTTP_HOST=HOST)
    assert response.status_code==302
    product.refresh_from_db();assert product.category_id==child.pk
    assert signed_in.post(base+'toggle/',HTTP_HOST=HOST).status_code==302
    assert signed_in.post(base+'delete/',HTTP_HOST=HOST).status_code==302


def test_category_count_distinguishes_hidden_items_from_website_products(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        child=MenuCategory.objects.create(name='Child',slug='child',parent=catalog['cat'])
        MenuItem.objects.create(name='Hidden podi',price=100,category=child,fulfilment='courier',active=False)
    listing=signed_in.get('/manage/categories/',HTTP_HOST=HOST)
    shelf=next(row['obj'] for row in listing.context['rows'] if row['obj'].pk==catalog['cat'].pk)
    assert shelf.product_count==2 and shelf.website_count==1
    assert b'1 on website' in listing.content
    assert b'Hidden podi' in signed_in.get(items_url(catalog['cat']),HTTP_HOST=HOST).content


def test_empty_categories_are_hidden_by_default_without_deleting_them(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        empty=MenuCategory.objects.create(name='Rice Mix Paste',slug='rice-mix-paste')
        parent=MenuCategory.objects.create(name='Parent shelf',slug='parent-shelf')
        child=MenuCategory.objects.create(name='Child shelf',slug='child-shelf',parent=parent)
        MenuItem.objects.create(name='Hidden product',category=child,price=100,active=False)
    page=signed_in.get('/manage/categories/',HTTP_HOST=HOST)
    ids={row['obj'].pk for row in page.context['rows']}
    assert empty.pk not in ids and parent.pk in ids and child.pk in ids
    assert page.context['total']==3
    assert page.context['category_tabs'][0]['selected']
    assert MenuCategory.all_tenants.filter(pk=empty.pk).exists()
    assert signed_in.get(items_url(empty),HTTP_HOST=HOST).status_code==200
    page=signed_in.get('/manage/categories/',{'category_view':'empty'},HTTP_HOST=HOST)
    assert {row['obj'].pk for row in page.context['rows']}=={empty.pk}
    assert page.context['category_tabs'][1]['selected']
    page=signed_in.get('/manage/categories/',{'category_view':'all'},HTTP_HOST=HOST)
    assert page.context['total']==4
    assert {row['obj'].pk for row in page.context['rows']}=={empty.pk,parent.pk,child.pk,catalog['cat'].pk}


def test_empty_category_search_and_pagination_keep_the_selected_view(signed_in,kitchens,catalog):
    with tenant_context(kitchens[0]):
        MenuCategory.objects.bulk_create([MenuCategory(tenant=kitchens[0],name=f'Empty {i}',slug=f'empty-{i}') for i in range(32)])
    page=signed_in.get('/manage/categories/',{'category_view':'empty','q':'Empty','page':2},HTTP_HOST=HOST)
    assert len(page.context['rows'])==2 and page.context['total']==32
    assert 'category_view=empty' in page.context['querystring']
    assert b'name="category_view" value="empty"' in page.content
    assert all('q=Empty' in tab['url'] and 'page=' not in tab['url'] for tab in page.context['category_tabs'])
    page=signed_in.get('/manage/categories/',{'category_view':'invalid'},HTTP_HOST=HOST)
    assert {row['obj'].pk for row in page.context['rows']}=={catalog['cat'].pk}
