"""Insert/move positions are independent between meal libraries and tenants."""
from django.db import transaction
from apps.tenancy.context import tenant_context
from apps.catalog.models import MenuItem
from apps.catalog.display_order import move, position, ordered
from apps.owner.tests.test_owner import kitchens


def test_inserting_and_moving_positions_compacts_each_list_without_touching_other_meals(kitchens):
    with tenant_context(kitchens[0]):
        a=MenuItem.objects.create(name='A shared',price=10,sort=1,tags=['meals:assigned','meal:breakfast','meal:lunch'])
        b=MenuItem.objects.create(name='B breakfast',price=10,sort=2,tags=['meals:assigned','meal:breakfast'])
        c=MenuItem.objects.create(name='C breakfast',price=10,sort=3,tags=['meals:assigned','meal:breakfast'])
        lunch=MenuItem.objects.create(name='Lunch only',price=10,sort=2,tags=['meals:assigned','meal:lunch'])
        move(c,1,group='breakfast',previous_sort=3)
        for row in [a,b,c,lunch]:row.refresh_from_db()
        assert [position(row,'breakfast') for row in [c,a,b]]==[1,2,3]
        assert [position(row,'lunch') for row in [a,lunch]]==[1,2]
        move(a,3,group='breakfast',previous_sort=a.sort)
        for row in [a,b,c,lunch]:row.refresh_from_db()
        assert [position(row,'breakfast') for row in [c,b,a]]==[1,2,3]
        assert [position(row,'lunch') for row in [a,lunch]]==[1,2]
        new=MenuItem.objects.create(name='New breakfast',price=10,sort=2,tags=['meals:assigned','meal:breakfast'])
        move(new,2,group='breakfast')
        for row in [a,b,c,new]:row.refresh_from_db()
        assert [position(row,'breakfast') for row in [c,new,b,a]]==[1,2,3,4]
        move(new,999,group='breakfast',previous_sort=new.sort)
        for row in [a,b,c,new]:row.refresh_from_db()
        assert [position(row,'breakfast') for row in [c,b,a,new]]==[1,2,3,4]
    with tenant_context(kitchens[1]):
        foreign=MenuItem.objects.create(name='Other store',price=10,sort=1,fulfilment='courier')
        assert foreign.display_positions=={}


def test_failed_save_rolls_back_shifted_positions(kitchens):
    with tenant_context(kitchens[0]):
        a=MenuItem.objects.create(name='A',price=10,sort=1,fulfilment='courier')
        b=MenuItem.objects.create(name='B',price=10,sort=2,fulfilment='courier')
        try:
            with transaction.atomic():
                move(b,1,group='shop',previous_sort=2)
                raise ValueError('Later validation failed')
        except ValueError:pass
        a.refresh_from_db();b.refresh_from_db()
        assert a.display_positions==b.display_positions=={} and b.sort==2
