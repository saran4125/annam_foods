"""Menu resolution.

Called by the storefront, the owner backend and the WhatsApp handler alike —
they are all the same function, not three HTTP endpoints that drift apart.
"""
from dataclasses import dataclass
from datetime import date as date_cls, datetime
from decimal import Decimal

from django.utils import timezone

from .models import MenuItem, MenuSchedule, ScheduleMode, Slot


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


def resolve_menu(on_date: date_cls, slot: Slot, include_unavailable: bool = False):
    """The menu for one date and slot.

    A dated row always beats the weekday template, which is what lets a kitchen
    that plans by week pull one dish on one day without editing the template.
    An item with neither row is simply not on the menu.

    Runs inside the current tenant's scope; callers must already be in one.
    """
    weekday = on_date.weekday()

    rows = (
        MenuSchedule.objects.filter(slot=slot)
        .filter(
            models_q_date(on_date) | models_q_weekday(weekday)
        )
        .select_related("item", "slot")
    )

    dated, weekly = {}, {}
    for row in rows:
        if row.mode == ScheduleMode.DATE:
            dated[row.item_id] = row
        else:
            weekly[row.item_id] = row

    chosen = {**weekly, **dated}  # dated overwrites weekly on collision

    entries = []
    for item_id, row in chosen.items():
        if not row.item.active:
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


def open_slots(on_date: date_cls, now=None):
    """Slots still accepting orders for a date, in display order."""
    return [
        s
        for s in Slot.objects.filter(active=True)
        if slot_is_open(s, on_date, now=now)
    ]
