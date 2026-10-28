"""Staff order groups use saved meal snapshots, never customer identity or live menus."""
from collections import Counter
from urllib.parse import urlencode

MEAL_ORDER = ('breakfast', 'lunch', 'snacks', 'dinner')
GROUP_LABELS = {
    'all': 'All orders',
    'breakfast': 'Breakfast',
    'lunch': 'Lunch',
    'dinner': 'Dinner',
    'snacks': 'Snacks / Shop',
    'breakfast+lunch': 'Breakfast + Lunch',
    'breakfast+snacks': 'Breakfast + Snacks',
    'lunch+snacks': 'Lunch + Snacks',
    'breakfast+lunch+snacks': 'Breakfast + Lunch + Snacks',
    'other': 'Other / review',
}


def meal_group(items, slot_key, fulfilment):
    keys = {line.get('meal_key') for line in (items or []) if line.get('meal_key')}
    if not keys:
        if slot_key in MEAL_ORDER:
            keys = {slot_key}
        elif fulfilment == 'courier':
            keys = {'snacks'}
    if not keys or not keys.issubset(MEAL_ORDER):
        return 'other'
    key = '+'.join(meal for meal in MEAL_ORDER if meal in keys)
    return key if key in GROUP_LABELS else 'other'


def grouped_orders(queryset, *, selected='', query='', status=''):
    selected = selected if selected in GROUP_LABELS else 'all'
    counts = Counter()
    selected_ids = []
    # Stream snapshots: no historical orders are rewritten and no live product
    # joins can reclassify an old order after menu edits.
    for pk, items, slot_key, fulfilment in queryset.values_list(
            'pk', 'items', 'slot__key', 'fulfilment').iterator(chunk_size=1000):
        key = meal_group(items, slot_key, fulfilment)
        counts[key] += 1
        if key == selected:
            selected_ids.append(pk)
    counts['all'] = sum(counts.values())
    tabs = []
    for key, label in GROUP_LABELS.items():
        always_visible = key in ('all', 'breakfast', 'lunch', 'dinner', 'snacks', 'breakfast+lunch')
        if not (always_visible or counts[key] or selected == key):
            continue
        tabs.append({'key': key, 'label': label, 'count': counts[key], 'active': selected == key,
                     'combined': '+' in key,
                     'url': '?' + urlencode({'meal_group': key, 'q': query, 'status': status})})
    if selected != 'all':
        queryset = queryset.filter(pk__in=selected_ids)
    return queryset, {
        'meal_group': selected, 'meal_group_label': GROUP_LABELS[selected],
        'meal_tabs': [tab for tab in tabs if not tab['combined']],
        'combined_tabs': [tab for tab in tabs if tab['combined']],
        'pagination_query': urlencode({'meal_group': selected, 'q': query, 'status': status}),
    }


def label_orders(orders):
    for order in orders:
        slot_key = order.slot.key if order.slot_id else None
        key = meal_group(order.items, slot_key, order.fulfilment)
        order.staff_meal_label = GROUP_LABELS[key]
