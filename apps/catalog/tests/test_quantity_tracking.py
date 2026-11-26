"""Optional quantities have the same semantics in billing and website orders."""
from datetime import timedelta
import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.owner.tests.test_owner import kitchens, owner, signed_in, catalog, HOST
from apps.catalog.models import MenuItem, MenuSchedule, StockReservation
from apps.catalog.inventory import configure, state
from apps.catalog.services import resolve_menu
from apps.billing.services import create_staff_order
from apps.orders.services import create_order, get_or_create_customer, RequestedLine, OrderError, advance_status
from apps.orders.models import Order
from apps.delivery.models import DeliveryZone
from apps.tenancy.context import tenant_context


def test_meal_stock_blocks_overselling_is_shared_and_restores_once(kitchens,catalog):
    tenant=kitchens[0];day=timezone.localdate()+timedelta(days=1)
    with tenant_context(tenant):
        slot=catalog['slot'];item=MenuItem.objects.create(name='Limited meal',price=100,tags=['meals:assigned','meal:lunch'])
        MenuSchedule.objects.create(item=item,slot=slot,mode='date',on_date=day)
        customer=get_or_create_customer(tenant,phone='919876543210',name='Quantity buyer')
        DeliveryZone.objects.create(pincode='600011',area_name='Test area',delivery_fee=10,min_order=0,slot_keys=['lunch'])
        configure(item,on_date=day,slot=slot,tracked=True,quantity=3)
        kwargs={'customer':customer,'slot':slot,'delivery_date':day,'address_snapshot':{'line1':'Test','pincode':'600011'},'payment_mode':'manual','website_checkout':True}
        before=Order.objects.count()
        with pytest.raises(OrderError):create_order(tenant,requested=[RequestedLine(item.pk,4,'lunch')],external_ref='too-many',**kwargs)
        assert Order.objects.count()==before and state(item,day,slot).remaining==3
        order=create_order(tenant,requested=[RequestedLine(item.pk,2,'lunch')],external_ref='limited-web',**kwargs)
        assert state(item,day,slot).remaining==1
        assert create_order(tenant,requested=[RequestedLine(item.pk,2,'lunch')],external_ref='limited-web',**kwargs).pk==order.pk
        assert state(item,day,slot).remaining==1
        with pytest.raises(OrderError):
            create_staff_order(tenant,name='Manual buyer',phone='919876543211',channel='manual',payment_mode='cod',requested=[(item.pk,2,'lunch')],delivery_date=day,token='too-many-manual',actor='test')
        manual=create_staff_order(tenant,name='Manual buyer',phone='919876543211',channel='manual',payment_mode='cod',requested=[(item.pk,1,'lunch')],delivery_date=day,token='last-manual',actor='test')
        assert state(item,day,slot).remaining==0 and not resolve_menu(day,slot)
        assert state(item,day+timedelta(days=1),slot) is None
        advance_status(order,'cancelled',actor='test');assert state(item,day,slot).remaining==2
        advance_status(order,'cancelled',actor='test');assert state(item,day,slot).remaining==2
        assert StockReservation.objects.filter(order=manual,released=False).count()==1


def test_shop_stock_defaults_off_and_revision_restock_are_safe(kitchens,catalog):
    with tenant_context(kitchens[0]):
        item=catalog['dish'];assert state(item) is None
        row=configure(item,tracked=True,quantity=3)
        with pytest.raises(ValidationError):configure(item,tracked=True,quantity=5,revision=0)
        row=configure(item,tracked=True,quantity=2,operation='add',revision=row.revision)
        assert row.remaining==5
        order=create_staff_order(kitchens[0],name='Stock buyer',phone='919876543215',channel='manual',payment_mode='cod',requested=[(item.pk,5,'snacks')],token='shop-stock',actor='test')
        assert state(item).remaining==0
        advance_status(order,'cancelled',actor='test');assert state(item).remaining==5
        current=state(item);configure(item,tracked=False,revision=current.revision)
        assert not state(item).tracked and state(item).remaining==5
