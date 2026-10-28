"""Meal tabs classify whole saved orders, including explicit combined orders."""
from datetime import time
import pytest
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST, OTHER
from apps.tenancy.context import tenant_context
from apps.catalog.models import Slot
from apps.orders.models import Order, Customer
from apps.owner.order_groups import meal_group


@pytest.fixture
def grouped(kitchens):
    with tenant_context(kitchens[0]):
        buyer = Customer.objects.create(name='Same customer', phone='919999999999')
        breakfast = Slot.objects.create(key='breakfast', label='Breakfast', order_cutoff=time(9))
        result = {}
        for name, keys in [('single-breakfast',['breakfast']),('single-lunch',['lunch']),
                           ('single-dinner',['dinner']),('single-snacks',['snacks']),
                           ('combined',['lunch','breakfast']),('all-three',['snacks','breakfast','lunch'])]:
            result[name] = Order.objects.create(order_no=name,customer=buyer,channel='web',
                subtotal=100,delivery_fee=10,total=110,
                items=[{'meal_key':key,'name':'Item','quantity':1} for key in keys],
                slot=breakfast if name=='combined' else None)
        result['legacy-breakfast'] = Order.objects.create(order_no='legacy-breakfast',customer=buyer,
            channel='manual',slot=breakfast,subtotal=100,total=100,items=[{'name':'Old item','quantity':1}])
        result['legacy-shop'] = Order.objects.create(order_no='legacy-shop',customer=buyer,
            channel='web',fulfilment='courier',subtotal=100,total=100,items=[{'name':'Old shop item','quantity':1}])
    with tenant_context(kitchens[1]):
        other = Customer.objects.create(name='Rival',phone='918888888888')
        Order.objects.create(order_no='PRIVATE-RIVAL-COMBO',customer=other,channel='web',subtotal=999,total=999,
            items=[{'meal_key':'breakfast'},{'meal_key':'lunch'}])
    return result


def test_combined_tab_shows_only_the_combined_order_without_merging_customer_orders(signed_in,grouped):
    response=signed_in.get('/manage/orders/',{'meal_group':'breakfast+lunch'},HTTP_HOST=HOST)
    assert response.status_code==200
    assert [o.pk for o in response.context['page']]==[grouped['combined'].pk]
    assert response.context['page'][0].staff_meal_label=='Breakfast + Lunch'
    assert response.context['page'][0].total==110
    assert b'PRIVATE-RIVAL-COMBO' not in response.content
    assert b'aria-current="page"' in response.content


@pytest.mark.parametrize('group,names',[
    ('breakfast',{'single-breakfast','legacy-breakfast'}),('lunch',{'single-lunch'}),
    ('dinner',{'single-dinner'}),('snacks',{'single-snacks','legacy-shop'}),
    ('breakfast+lunch+snacks',{'all-three'}),('all',{'single-breakfast','single-lunch','single-dinner','single-snacks','combined','all-three','legacy-breakfast','legacy-shop'}),
])
def test_meal_groups_are_exact_and_support_legacy_snapshots(signed_in,grouped,group,names):
    response=signed_in.get('/manage/orders/',{'meal_group':group},HTTP_HOST=HOST)
    assert {o.order_no for o in response.context['page']}==names


def test_search_status_counts_and_pagination_preserve_the_selected_group(signed_in,kitchens,grouped):
    with tenant_context(kitchens[0]):
        order=grouped['combined']
        Order.objects.filter(pk=order.pk).update(status='confirmed')
        for i in range(31):
            Order.objects.create(order_no=f'page-combo-{i}',customer=order.customer,channel='manual',status='confirmed',
                subtotal=100,total=100,items=[{'meal_key':'breakfast'},{'meal_key':'lunch'}])
    response=signed_in.get('/manage/orders/',{'meal_group':'breakfast+lunch','status':'confirmed','q':'page-'},HTTP_HOST=HOST)
    assert response.context['page'].paginator.count==31
    combined=next(t for t in response.context['combined_tabs'] if t['active'])
    assert combined['count']==31
    html=response.content.decode()
    assert 'meal_group=breakfast%2Blunch' in html and 'status=confirmed' in html and 'q=page-' in html
    assert 'name="meal_group" value="breakfast+lunch"' in html
    response=signed_in.get('/manage/orders/',{'meal_group':'breakfast+lunch','status':'confirmed','q':'page-','page':2},HTTP_HOST=HOST)
    assert len(response.context['page'])==1


def test_unknown_group_defaults_to_all_and_staff_scope_is_enforced(signed_in,grouped):
    response=signed_in.get('/manage/orders/',{'meal_group':'not-valid'},HTTP_HOST=HOST)
    assert response.context['meal_group']=='all' and response.context['page'].paginator.count==8
    assert signed_in.get('/manage/orders/',HTTP_HOST=OTHER).status_code==403


def test_unknown_or_invalid_legacy_combinations_stay_visible_for_review():
    assert meal_group([{'meal_key':'unclassified'}],None,'scheduled')=='other'
    assert meal_group([{'meal_key':'dinner'},{'meal_key':'lunch'}],None,'scheduled')=='other'
    assert meal_group([],None,'scheduled')=='other'
