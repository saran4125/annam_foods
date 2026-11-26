"""Master meal membership is independent from daily availability."""
from django.db import transaction
from django.db.models import Q
from apps.tenancy.context import get_current_tenant
from apps.tenancy.models import Tenant
from .models import MenuCategory, MenuItem, Slot

MEALS = {'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner'}
DEFAULTS = {**MEALS, 'shop': 'Shop'}

@transaction.atomic
def ensure_defaults():
    tenant = get_current_tenant()
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    for sort, (key, name) in enumerate(DEFAULTS.items()):
        MenuCategory.objects.get_or_create(slug=key, defaults={'name': name, 'sort': sort})
        if key in MEALS:
            Slot.objects.get_or_create(key=key, defaults={'label': name, 'sort': sort, 'order_cutoff': '23:59:59'})

def meal_keys(item):
    if item.fulfilment != 'scheduled':
        return []
    if 'meals:assigned' in (item.tags or []):
        return [key for key in MEALS if 'meal:' + key in item.tags]
    keys = {row.slot.key for row in item.schedule.all()}
    if item.category_id and item.category.slug in MEALS:
        keys.add(item.category.slug)
    return [key for key in MEALS if key in keys]

def for_meal(items, key):
    return items.filter(Q(tags__contains=['meal:' + key]) | (~Q(tags__contains=['meals:assigned']) & (Q(schedule__slot__key=key) | Q(category__slug=key)))).distinct()

def category_items(category):
    if category.slug in MEALS:
        return for_meal(MenuItem.objects.filter(fulfilment='scheduled'), category.slug)
    if category.slug == 'shop':
        return MenuItem.objects.filter(fulfilment='courier')
    from .services import category_family_ids
    return MenuItem.objects.filter(category_id__in=category_family_ids(category))


@transaction.atomic
def remove_category(category):
    """Delete a shelf, preserving its products, stock and historical snapshots."""
    from django.core.exceptions import ValidationError
    tenant=get_current_tenant()
    if category.tenant_id != tenant.pk:
        raise ValidationError('Choose a category from this store.')
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if category.slug in DEFAULTS:
        raise ValidationError('Default categories stay available. Use the visibility switch to hide one.')
    MenuItem.objects.filter(category=category).update(category=None)
    MenuCategory.objects.filter(parent=category).update(parent=None)
    category.delete()
