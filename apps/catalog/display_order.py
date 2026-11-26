"""Insert dishes into numbered meal/shop lists under one store lock."""
from django.db import transaction
from django.db.models import F, IntegerField
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from apps.tenancy.context import get_current_tenant
from apps.tenancy.models import Tenant
from .models import MenuItem
from .library import MEALS, for_meal, meal_keys

GROUPS = (*MEALS, 'shop')


def position(item, group):
    return (item.display_positions or {}).get(group, item.sort)


def ordered(items, group):
    return sorted(items, key=lambda i: (position(i,group), -i.sort_priority, i.name, i.pk))


def with_position(items, group):
    if group not in GROUPS:
        return items.annotate(display_position=F('sort'))
    return items.annotate(display_position=Coalesce(Cast(KeyTextTransform(group,'display_positions'),IntegerField()),F('sort'),output_field=IntegerField()))


def lock_store():
    tenant=get_current_tenant()
    Tenant.objects.select_for_update().get(pk=tenant.pk)


@transaction.atomic
def move(item, requested, *, group=None, previous_sort=None):
    tenant=get_current_tenant()
    if item.tenant_id != tenant.pk:
        raise ValueError('Choose a dish from this store.')
    lock_store()
    keys=['shop'] if item.fulfilment=='courier' else meal_keys(item)
    if not keys:
        return
    group=group if group in keys else keys[0]
    # Snapshot every group's current order before changing any shared dish map.
    rows=list(MenuItem.objects.select_related('category').prefetch_related('schedule__slot'))
    by_id={row.pk:row for row in rows}
    target=by_id[item.pk]
    target.sort=previous_sort if previous_sort is not None else target.sort
    lists={}
    for key in GROUPS:
        members=[row for row in rows if (row.fulfilment=='courier' if key=='shop' else key in meal_keys(row))]
        peers=ordered([row for row in members if row.pk!=item.pk],key)
        if key in keys:
            if key==group:
                index=max(0,min(int(requested)-1,len(peers)))
            elif previous_sort is None:
                index=len(peers)
            else:
                current=ordered(members,key)
                index=next(i for i,row in enumerate(current) if row.pk==item.pk)
            peers.insert(index,target)
        lists[key]=peers
    positions={row.pk:{} for row in rows}
    for key,members in lists.items():
        for number,row in enumerate(members,1):positions[row.pk][key]=number
    changed=[]
    for row in rows:
        if row.display_positions!=positions[row.pk]:
            row.display_positions=positions[row.pk];changed.append(row)
    if changed:MenuItem.objects.bulk_update(changed,['display_positions'])
    item.display_positions=positions[item.pk]
    item.sort=item.display_positions[group]
    MenuItem.objects.filter(pk=item.pk).update(sort=item.sort)
