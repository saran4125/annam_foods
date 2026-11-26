"""Atomic stock shared by website checkout and manual billing."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from apps.tenancy.models import Tenant
from apps.tenancy.context import get_current_tenant
from .models import InventoryBucket, StockReservation, MenuItem, MenuSchedule, Slot


def bucket_key(item, on_date=None, slot=None):
    if item.fulfilment == 'scheduled':
        return f'm:{on_date}:{slot.pk}:{item.pk}' if on_date and slot else None
    return f'p:{item.pk}'

def state(item, on_date=None, slot=None):
    key = bucket_key(item, on_date, slot)
    return InventoryBucket.objects.filter(bucket_key=key).first() if key else None

def decorate(item, on_date=None, slot=None):
    bucket = state(item, on_date, slot)
    item.quantity_tracked = bool(bucket and bucket.tracked)
    item.stock_quantity = bucket.remaining if bucket else 0
    return item

@transaction.atomic
def configure(item, *, on_date=None, slot=None, tracked=False, quantity=0, operation='set', revision=0):
    tenant = get_current_tenant()
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if item.tenant_id != tenant.pk or (slot and slot.tenant_id != tenant.pk):
        raise ValidationError('Choose an item and meal from this store.')
    if item.fulfilment == 'scheduled' and (not slot or not on_date or on_date < timezone.localdate()):
        raise ValidationError('Choose today or a future delivery date and meal.')
    if operation not in ('set', 'add') or not isinstance(quantity, int) or not 0 <= quantity <= 1000000000:
        raise ValidationError('Enter a non-negative whole quantity and a valid operation.')
    key = bucket_key(item, on_date, slot)
    row = InventoryBucket.objects.select_for_update().filter(bucket_key=key).first()
    if (row.revision if row else 0) != revision:
        raise ValidationError('Stock changed since this form opened. Reload and review the latest quantity.')
    remaining = (row.remaining if row else 0)
    if tracked:
        remaining = remaining + quantity if operation == 'add' else quantity
    if remaining > 1000000000:
        raise ValidationError('The resulting quantity is too large.')
    if row:
        row.tracked, row.remaining = tracked, remaining
        row.revision += 1
        row.save(update_fields=['tracked', 'remaining', 'revision'])
    else:
        row = InventoryBucket.objects.create(item=item, bucket_key=key, slot=slot if item.fulfilment == 'scheduled' else None, on_date=on_date if item.fulfilment == 'scheduled' else None, tracked=tracked, remaining=remaining)
    # Remove legacy exact-date limits only; do not freeze the rest of the menu.
    if item.fulfilment == 'scheduled':
        exact=MenuSchedule.objects.filter(item=item, slot=slot, mode='date', on_date=on_date)
        if exact.exists(): exact.update(qty_limit=None)
        else:
            from .services import effective_menu_rows
            source=effective_menu_rows(on_date,slot).get(item.pk)
            if source is None or source.qty_limit is not None:
                MenuSchedule.objects.create(item=item,slot=slot,mode='date',on_date=on_date,available=source.available if source else False,qty_limit=None,price_override=source.price_override if source else None)
    return row

@transaction.atomic
def reserve(order):
    from apps.orders.services import OrderError
    from .services import effective_menu_rows
    tenant=get_current_tenant()
    if tenant is None or order.tenant_id!=tenant.pk: raise ValueError('Order does not belong to this store.')
    Tenant.objects.select_for_update().get(pk=order.tenant_id)
    totals = {}
    for line in order.items:
        item = MenuItem.objects.get(pk=line['item_id'])
        if not item.active or not item.in_stock: raise OrderError('An item is no longer in stock.')
        slot = Slot.objects.filter(key=line.get('meal_key')).first() if item.fulfilment == 'scheduled' else None
        on_date = order.delivery_date or timezone.localdate()
        bucket = state(item, on_date, slot)
        schedule = None
        if item.fulfilment == 'scheduled' and not slot and InventoryBucket.objects.filter(item=item, on_date=on_date, tracked=True).exists():
            raise OrderError('Choose the meal and delivery date for ' + item.name + '.')
        if slot:
            row = effective_menu_rows(on_date, slot).get(item.pk)
            if row and row.qty_limit is not None and not (bucket and bucket.tracked):
                schedule, _ = MenuSchedule.objects.get_or_create(item=item, slot=slot, mode='date', on_date=on_date, defaults={'available': row.available, 'qty_limit': row.qty_limit, 'price_override': row.price_override})
        if not (bucket and bucket.tracked) and not schedule:
            continue
        key = f'bucket:{bucket.pk}' if bucket and bucket.tracked else f'schedule:{schedule.pk}'
        entry = totals.setdefault(key, {'bucket': bucket if bucket and bucket.tracked else None, 'schedule': schedule, 'quantity': 0, 'name': item.name})
        entry['quantity'] += int(line['quantity'])
    for key, data in totals.items():
        if StockReservation.objects.filter(order=order, reservation_key=key).exists():
            continue
        q, bucket, schedule = data['quantity'], data['bucket'], data['schedule']
        if bucket and not InventoryBucket.objects.filter(pk=bucket.pk, tracked=True, remaining__gte=q).update(remaining=F('remaining')-q, revision=F('revision')+1):
            raise OrderError('Not enough stock for ' + data['name'] + '.')
        if schedule and not MenuSchedule.objects.filter(pk=schedule.pk, qty_sold__lte=F('qty_limit')-q).update(qty_sold=F('qty_sold')+q):
            raise OrderError('Not enough portions for ' + data['name'] + '.')
        StockReservation.objects.create(order=order, reservation_key=key, bucket=bucket, schedule=schedule, quantity=q)

@transaction.atomic
def release(order):
    tenant=get_current_tenant()
    if tenant is None or order.tenant_id!=tenant.pk: raise ValueError('Order does not belong to this store.')
    Tenant.objects.select_for_update().get(pk=order.tenant_id)
    for row in StockReservation.objects.select_for_update().filter(order=order, released=False):
        if row.bucket_id:
            InventoryBucket.objects.filter(pk=row.bucket_id).update(remaining=F('remaining')+row.quantity, revision=F('revision')+1)
        if row.schedule_id:
            MenuSchedule.objects.filter(pk=row.schedule_id).update(qty_sold=F('qty_sold')-row.quantity)
        row.released = True
        row.save(update_fields=['released'])
