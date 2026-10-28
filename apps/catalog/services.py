"""Menu resolution.

Called by the storefront, the owner backend and the WhatsApp handler alike —
they are all the same function, not three HTTP endpoints that drift apart.
"""
from dataclasses import dataclass
from datetime import date as date_cls, datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import MenuCategory, MenuItem, MenuSchedule, ScheduleMode, Slot, MenuDay


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


def resolve_menu(on_date: date_cls, slot: Slot, include_unavailable: bool = False, *, include_inactive=False):
    """The menu for one date and slot.

    An explicitly saved MenuDay uses only dated rows, including an empty menu.
    Otherwise dated rows override the weekday template dish by dish. Existing
    schedules are preserved until staff save the actual date's full menu.
    An item with neither row is simply not on the menu.

    Runs inside the current tenant's scope; callers must already be in one.
    """
    weekday = on_date.weekday()

    date_only = MenuDay.objects.filter(slot=slot, on_date=on_date).exists()
    condition = models_q_date(on_date) if date_only else models_q_date(on_date) | models_q_weekday(weekday)
    rows = MenuSchedule.objects.filter(slot=slot).filter(condition).select_related("item", "slot")

    dated, weekly = {}, {}
    for row in rows:
        if row.mode == ScheduleMode.DATE:
            dated[row.item_id] = row
        else:
            weekly[row.item_id] = row

    chosen = {**weekly, **dated}  # dated overwrites weekly on collision

    entries = []
    for item_id, row in chosen.items():
        if row.item.fulfilment != "scheduled" or (not row.item.active and not include_inactive):
            continue
        entry = MenuEntry(
            item=row.item,
            slot=row.slot,
            price=row.effective_price,
            available=row.available,
            sold_out=row.is_sold_out,
            source=row.mode,
        )
        if include_unavailable or entry.is_orderable:
            entries.append(entry)

    entries.sort(key=lambda e: (e.item.sort, e.item.name))
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
    return Slot.objects.filter(active=True, order_cutoff__gt=now.time()).order_by(
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
        for s in Slot.objects.filter(active=True)
        if slot_is_open(s, on_date, now=now)
    ]


# -- the shop: courier goods browsed by category ------------------------------

SHOP_SORTS = {
    "featured": ("category__sort", "sort", "name"),
    "price": ("price", "name"),
    "-price": ("-price", "name"),
    "name": ("name",),
}


def shop_items():
    """Every courier item currently on sale, whatever its category."""
    return MenuItem.objects.filter(active=True, fulfilment="courier").select_related("category")


def shop_categories():
    """Top-level shop shelves that have something to sell, with live counts.

    A parent shelf (Pakshanams) counts the goods on its child shelves
    (Murukku, Chips...), because that is how a customer reads it."""
    categories = list(
        MenuCategory.objects.filter(active=True).exclude(slug="").select_related("parent")
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
        if c.parent_id is None and totals.get(c.id):
            c.item_count = totals[c.id]
            shelves.append(c)
    return shelves


def category_family_ids(category):
    """A shelf and every shelf beneath it."""
    ids, frontier = {category.id}, [category.id]
    while frontier:
        children = list(
            MenuCategory.objects.filter(parent_id__in=frontier, active=True).values_list("id", flat=True)
        )
        frontier = [c for c in children if c not in ids]
        ids.update(frontier)
    return ids


def search_shop(*, category=None, query="", sort="featured"):
    """Shop listing: optional shelf, free-text search, a known sort order."""
    items = shop_items()
    if category is not None:
        items = items.filter(category_id__in=category_family_ids(category))
    query = (query or "").strip()[:80]
    if query:
        from django.db.models import Q

        for word in query.split()[:5]:
            items = items.filter(Q(name__icontains=word) | Q(description__icontains=word))
    return items.order_by(*SHOP_SORTS.get(sort, SHOP_SORTS["featured"]))
