"""Menu resolution.

Called by the storefront, the owner backend and the WhatsApp handler alike —
they are all the same function, not three HTTP endpoints that drift apart.
"""
from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import MenuCategory, MenuItem, MenuSchedule, ScheduleMode, Slot, MenuDay
from apps.tenancy.context import get_current_tenant


@dataclass(frozen=True)
class MenuEntry:
    """One dish, as offered on a particular date and slot."""

    item: MenuItem
    slot: Slot
    price: Decimal
    available: bool
    sold_out: bool
    source: str  # "date" or "weekday" — which row decided this

    @property
    def is_orderable(self) -> bool:
        return self.available and not self.sold_out


def meal_carries_forward(slot):
    tenant = get_current_tenant()
    if not tenant or tenant.pk != slot.tenant_id or slot.key not in ('breakfast', 'lunch', 'dinner'):
        return False
    if 'carry_forward_meals' in tenant.config.features:
        return tenant.feature('carry_forward_meals')
    # Preserve the earlier breakfast-only setting until the store is upgraded.
    return slot.key == 'breakfast' and tenant.feature('carry_forward_breakfast')


def effective_menu_rows(on_date, slot):
    """Choose scoped rows; a saved date always overrides an inherited default."""
    date_only = MenuDay.objects.filter(slot=slot, on_date=on_date).exists()
    previous = None
    if not date_only and meal_carries_forward(slot):
        previous = MenuDay.objects.filter(slot=slot, on_date__lt=on_date).order_by('-on_date').first()
    if date_only:
        condition = models_q_date(on_date)
    elif previous:
        condition = models_q_date(previous.on_date) | models_q_date(on_date)
    else:
        condition = models_q_date(on_date) | models_q_weekday(on_date.weekday())
    rows = MenuSchedule.objects.filter(slot=slot).filter(condition).select_related("item", "slot")
    dated, defaults = {}, {}
    for row in rows:
        if row.mode == ScheduleMode.DATE and row.on_date == on_date:
            dated[row.item_id] = row
        else:
            defaults[row.item_id] = row
    return {**defaults, **dated}


def resolve_menu(on_date: date_cls, slot: Slot, include_unavailable: bool = False, *, include_inactive=False):
    """Resolve a saved date, opted-in meal default, or legacy weekly menu.

    Explicitly saved empty menus remain empty. Inherited meal rows get fresh
    daily quantities; the source date's sales never make tomorrow sold out.
    """
    chosen = effective_menu_rows(on_date, slot)
    entries = []
    for item_id, row in chosen.items():
        if row.item.fulfilment != "scheduled" or (not row.item.active and not include_inactive):
            continue
        from .inventory import decorate
        decorate(row.item, on_date, slot)
        inherited = row.mode == ScheduleMode.DATE and row.on_date != on_date
        sold_out = (row.qty_limit is not None and row.qty_limit <= 0) if inherited else row.is_sold_out
        entry = MenuEntry(
            item=row.item,
            slot=row.slot,
            price=row.effective_price,
            available=row.available,
            sold_out=sold_out or not row.item.in_stock or (row.item.quantity_tracked and row.item.stock_quantity == 0),
            source=row.mode,
        )
        if include_unavailable or entry.is_orderable:
            entries.append(entry)

    from .display_order import position
    entries.sort(key=lambda e: (position(e.item,slot.key), -e.item.sort_priority, e.item.name, e.item.pk))
    return entries


def models_q_date(on_date):
    from django.db.models import Q

    return Q(mode=ScheduleMode.DATE, on_date=on_date)


def models_q_weekday(weekday):
    from django.db.models import Q

    return Q(mode=ScheduleMode.WEEKDAY, weekday=weekday)


def slot_is_open(slot: Slot, on_date: date_cls, now=None) -> bool:
    """Can an order still be placed for this slot on this date?

    A menu that lets someone order lunch at 2pm produces an angry phone call,
    so the cutoff is enforced here rather than left to the template.
    """
    now = now or timezone.localtime()
    cutoff = timezone.make_aware(
        datetime.combine(on_date, slot.order_cutoff), now.tzinfo
    )
    return now < cutoff


def current_customer_slot(*, now=None):
    """Only the next active meal before its local cutoff accepts web orders.

    Configured cutoffs define consecutive ordering periods. Sorting by cutoff
    rather than display order keeps a rearranged menu from opening dinner early.
    Tomorrow supports advance orders for any active meal.
    """
    now = now or timezone.localtime()
    return Slot.objects.exclude(key__in=['snack','snacks']).filter(active=True, order_cutoff__gt=now.time()).order_by(
        'order_cutoff', 'sort', 'key').first()


def customer_slot_is_open(slot, on_date, *, now=None):
    now = now or timezone.localtime()
    if not slot.active or on_date not in (now.date(), now.date() + timedelta(days=1)):
        return False
    opening_day = on_date - timedelta(days=slot.order_days_before)
    opening = timezone.make_aware(datetime.combine(opening_day, slot.order_opens_at), now.tzinfo)
    closing = timezone.make_aware(datetime.combine(on_date, slot.order_cutoff), now.tzinfo)
    return opening <= now < closing


def open_slots(on_date: date_cls, now=None):
    """Slots still accepting orders for a date, in display order."""
    return [
        s
        for s in Slot.objects.exclude(key__in=['snack','snacks']).filter(active=True)
        if slot_is_open(s, on_date, now=now)
    ]


# -- the shop: courier goods browsed by category ------------------------------

SHOP_SORTS = {
    "featured": ("display_position", "-sort_priority", "name", "pk"),
    "price": ("price", "name", "pk"),
    "-price": ("-price", "name", "pk"),
    "name": ("name", "pk"),
}


def shop_items():
    """Every courier item currently on sale, whatever its category."""
    return MenuItem.objects.filter(active=True, in_stock=True, fulfilment="courier").exclude(inventorybucket__tracked=True,inventorybucket__remaining=0).select_related("category")


def shop_categories():
    """Top-level shop shelves that have something to sell, with live counts.

    A parent shelf (Pakshanams) counts the goods on its child shelves
    (Murukku, Chips...), because that is how a customer reads it."""
    categories = list(
        MenuCategory.objects.filter(active=True).exclude(slug="").select_related("parent").order_by("sort","name","pk")
    )
    counts = {}
    for category_id in shop_items().values_list("category_id", flat=True):
        counts[category_id] = counts.get(category_id, 0) + 1
    by_id = {c.id: c for c in categories}
    totals = {}
    for c in categories:
        top, depth = c, 0
        while top.parent_id and top.parent_id in by_id and depth < 6:  # a bad edit can loop
            top, depth = by_id[top.parent_id], depth + 1
        totals[top.id] = totals.get(top.id, 0) + counts.get(c.id, 0)
    shelves = []
    for c in categories:
        count=sum(counts.values()) if c.slug=='shop' else totals.get(c.id,0)
        if (c.parent_id is None or c.slug=='shop') and count:
            c.item_count = count
            shelves.append(c)
    return shelves


def category_families(categories):
    """Resolve active descendants in memory, including corrupt-cycle protection."""
    children={}
    for category in categories:
        if category.active:children.setdefault(category.parent_id,[]).append(category.pk)
    families={}
    for root in categories:
        ids={root.pk};frontier=[root.pk]
        while frontier:
            following={pk for parent in frontier for pk in children.get(parent,[]) if pk not in ids}
            ids.update(following);frontier=list(following)
        families[root.pk]=ids
    return families


def category_family_ids(category):
    return category_families(list(MenuCategory.objects.all())).get(category.pk,{category.pk})


def shop_subcategories(category):
    """Two queries regardless of how many child categories are displayed."""
    from django.db.models import Count
    categories=list(MenuCategory.objects.all());families=category_families(categories)
    counts=dict(shop_items().order_by().values('category_id').annotate(n=Count('pk')).values_list('category_id','n'))
    return [child for child in categories if child.active and child.slug and child.parent_id==category.pk
            and any(counts.get(pk,0) for pk in families[child.pk])]


def search_shop(*, category=None, query="", sort="featured"):
    """Shop listing: optional shelf, free-text search, a known sort order."""
    items = shop_items()
    if category is not None and category.slug != 'shop':
        items = items.filter(category_id__in=category_family_ids(category))
    query = (query or "").strip()[:80]
    if query:
        from django.db.models import Q

        for word in query.split()[:5]:
            items = items.filter(Q(name__icontains=word) | Q(description__icontains=word))
    from .display_order import with_position
    return with_position(items,"shop").order_by(*SHOP_SORTS.get(sort, SHOP_SORTS["featured"]))


def popular_shop_items(limit=12):
    """Explicit home favourites first; saved display order within each group."""
    from .display_order import with_position
    items=list(with_position(shop_items(),'shop').order_by('display_position','-sort_priority','name','pk'))
    featured=[item for item in items if 'featured' in (item.tags or [])][:limit]
    selected={item.pk for item in featured}
    return featured+[item for item in items if item.pk not in selected][:max(0,limit-len(featured))]


def assign_display_priority(item):
    """Record an explicit display-order save, separately from stock/status writes."""
    from time import time_ns
    item.sort_priority = time_ns() // 1000


def published_menu(on_date, slot):
    """Display scheduled dishes, including sold out; keep removed rows hidden."""
    return [entry for entry in resolve_menu(on_date,slot,include_unavailable=True) if entry.available]
