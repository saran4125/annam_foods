"""Menu group selection uses saved schedules, never category-name guesses."""
from django.db.models import Count

from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, Slot


def menu_selection(params):
    kind = 'courier' if params.get('type') == 'courier' else 'scheduled'
    slots = list(Slot.objects.all())
    keys = {slot.key: slot for slot in slots}
    requested = params.get('meal', '')
    if requested == 'unassigned' or not slots:
        return {'kind': kind, 'slot': None, 'meal': 'unassigned', 'label': 'Not assigned', 'slots': slots}
    default = keys.get('breakfast') or (slots[0] if slots else None)
    slot = keys.get(requested) or default
    return {'kind': kind, 'slot': slot, 'meal': slot.key, 'label': slot.label, 'slots': slots}


def menu_items(selection):
    items = MenuItem.objects.filter(fulfilment=selection['kind'])
    if selection['kind'] == 'courier':
        return items
    if selection['slot'] is None:
        return items.filter(schedule__isnull=True)
    return items.filter(schedule__slot=selection['slot']).distinct()


def menu_group_counts():
    items = MenuItem.objects.all()
    counts = dict(items.values('fulfilment').annotate(total=Count('pk')).values_list('fulfilment', 'total'))
    per_slot = dict(MenuSchedule.objects.filter(item__fulfilment='scheduled')
                    .values('slot_id').annotate(total=Count('item_id', distinct=True)).values_list('slot_id', 'total'))
    return {'meals': counts.get('scheduled', 0), 'other': counts.get('courier', 0),
            'unassigned': items.filter(fulfilment='scheduled', schedule__isnull=True).count(), 'slots': per_slot}


def menu_categories(items):
    return MenuCategory.objects.filter(pk__in=items.values('category_id')).order_by('sort', 'name')
