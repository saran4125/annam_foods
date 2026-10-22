"""Menu group selection uses saved schedules, never category-name guesses."""
from datetime import date
from django.http import Http404
from django.utils import timezone
from django.db.models import Count

from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, Slot, MenuDay


def menu_selection(params):
    kind = 'courier' if params.get('type') == 'courier' else 'scheduled'
    slots = list(Slot.objects.all())
    keys = {slot.key: slot for slot in slots}
    requested = params.get('meal', '')
    raw_date = params.get('date', timezone.localdate().isoformat())
    try:
        on_date = None if raw_date == 'all' or kind == 'courier' else date.fromisoformat(raw_date)
    except (TypeError, ValueError):
        raise Http404('Choose a valid menu date.')
    if requested == 'unassigned' or not slots:
        return {'kind': kind, 'slot': None, 'meal': 'unassigned', 'label': 'Not assigned', 'slots': slots, 'on_date': on_date}
    default = keys.get('breakfast') or (slots[0] if slots else None)
    slot = keys.get(requested) or default
    return {'kind': kind, 'slot': slot, 'meal': slot.key, 'label': slot.label, 'slots': slots, 'on_date': on_date}


def menu_items(selection):
    items = MenuItem.objects.filter(fulfilment=selection['kind'])
    if selection['kind'] == 'courier':
        return items
    if selection['slot'] is None:
        return items.filter(schedule__isnull=True)
    if selection['on_date']:
        from apps.catalog.services import resolve_menu
        entries = resolve_menu(selection['on_date'], selection['slot'], include_unavailable=True, include_inactive=True)
        return items.filter(pk__in=[entry.item.pk for entry in entries if entry.available])
    return items.filter(schedule__slot=selection['slot']).distinct()


def menu_group_counts(on_date=None):
    items = MenuItem.objects.all()
    counts = dict(items.values('fulfilment').annotate(total=Count('pk')).values_list('fulfilment', 'total'))
    per_slot = dict(MenuSchedule.objects.filter(item__fulfilment='scheduled')
                    .values('slot_id').annotate(total=Count('item_id', distinct=True)).values_list('slot_id', 'total'))
    if on_date:
        from apps.catalog.services import resolve_menu
        per_slot = {slot.pk: sum(entry.available for entry in resolve_menu(on_date, slot, include_unavailable=True, include_inactive=True)) for slot in Slot.objects.all()}
    return {'meals': counts.get('scheduled', 0), 'other': counts.get('courier', 0),
            'unassigned': items.filter(fulfilment='scheduled', schedule__isnull=True).count(), 'slots': per_slot}


def menu_categories(items):
    return MenuCategory.objects.filter(pk__in=items.values('category_id')).order_by('sort', 'name')
