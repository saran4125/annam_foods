"""Order creation — the single entry point for every channel.

The website calls this. The WhatsApp flow will call this. Neither one gets to
decide what anything costs: every line is re-priced from the live menu here,
so a stale price in a browser session or a WhatsApp payload cannot decide what
a customer pays.

Failures raise typed errors the caller turns into a message. They are
exceptions rather than return codes because an order that cannot be created
must not be half-created.
"""
import random
from dataclasses import dataclass
from datetime import date as date_cls
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Slot
from apps.catalog.services import resolve_menu, slot_is_open
from apps.delivery.services import zones_for_pincode

from .models import (
    STATUS_FLOW,
    TERMINAL,
    Address,
    Channel,
    Customer,
    Order,
    OrderEvent,
    OrderStatus,
    OrderSource,
    PaymentMode,
    PaymentStatus,
)


class OrderError(Exception):
    """Base for anything that stops an order being created."""


class KitchenNotAccepting(OrderError): ...
class SlotClosed(OrderError): ...
class EmptyOrder(OrderError): ...
class ItemNotOnMenu(OrderError): ...
class NotServiceable(OrderError): ...
class BelowMinimum(OrderError):
    def __init__(self, shortfall: Decimal, minimum: Decimal):
        self.shortfall, self.minimum = shortfall, minimum
        super().__init__(f"₹{shortfall:.0f} below the ₹{minimum:.0f} minimum")
class InvalidTransition(OrderError): ...


@dataclass(frozen=True)
class RequestedLine:
    """What a caller asked for. Deliberately carries no price."""
    item_id: int
    quantity: int


def generate_order_number(tenant, on_date: date_cls | None = None) -> str:
    """A customer-facing reference, e.g. ANNAM-20260907-4812.

    Gaps are fine here — this is a reference, not an invoice series. Invoice
    numbers must be gapless and are allocated separately, under a row lock,
    which is why they wait for PostgreSQL.
    """
    on_date = on_date or timezone.localdate()
    prefix = tenant.slug.upper()[:10]
    return f"{prefix}-{on_date:%Y%m%d}-{random.randint(1000, 9999)}"


def _priced_menu(delivery_date: date_cls, slot: Slot) -> dict:
    return {entry.item.id: entry for entry in resolve_menu(delivery_date, slot)}


def price_lines(requested, *, delivery_date: date_cls, slot: Slot):
    """Turn requested quantities into priced snapshot lines.

    Raises rather than silently dropping: a caller asking for something that
    isn't on the menu has a stale page, and quietly shipping a smaller order
    than someone thought they placed is worse than telling them.
    """
    if not requested:
        raise EmptyOrder("An order needs at least one item.")

    priced = _priced_menu(delivery_date, slot)
    lines, subtotal = [], Decimal("0")

    for want in requested:
        if want.quantity <= 0:
            continue
        entry = priced.get(want.item_id)
        if entry is None:
            raise ItemNotOnMenu(f"Item {want.item_id} is not on this menu.")
        line_total = entry.price * want.quantity
        subtotal += line_total
        lines.append({
            "item_id": entry.item.id,
            "name": entry.item.name,
            "unit_price": str(entry.price),
            "quantity": want.quantity,
            "line_total": str(line_total),
            "is_veg": entry.item.is_veg,
        })

    if not lines:
        raise EmptyOrder("An order needs at least one item.")
    return lines, subtotal


def get_or_create_customer(tenant, *, phone: str, name: str = "",
                           email: str = "", channel: str = Channel.WEB) -> Customer:
    customer, created = Customer.objects.get_or_create(
        phone=phone,
        defaults={"name": name, "email": email, "source": channel, "tenant": tenant},
    )
    changed = []
    if not created:
        customer.last_seen = timezone.now()
        changed.append("last_seen")
        if name and not customer.name:
            customer.name = name
            changed.append("name")
        if email and not customer.email:
            customer.email = email
            changed.append("email")
        customer.save(update_fields=changed)
    return customer


@transaction.atomic
def create_order(tenant, *, customer: Customer, requested, slot: Slot,
                 delivery_date: date_cls, address: Address | None = None,
                 address_snapshot: dict | None = None,
                 channel: str = Channel.WEB, source: str | None = None,
                 payment_mode: str = PaymentMode.ONLINE, now=None) -> Order:
    """Create one order, or raise. Both channels come through here.

    Validates in the order a customer would hit the problems: is the kitchen
    open for business, is this slot still orderable, is the food actually on
    the menu, do we deliver there, and is it worth sending a rider for.
    """
    if not tenant.can_take_orders:
        raise KitchenNotAccepting("This kitchen isn't accepting orders right now.")
    source = source or {Channel.WEB: OrderSource.STOREFRONT,
                        Channel.WHATSAPP: OrderSource.WA_CHAT,
                        Channel.MANUAL: OrderSource.OWNER}[channel]
    if source not in OrderSource.values or payment_mode not in PaymentMode.values:
        raise OrderError("Unknown order source or payment mode.")

    if not slot_is_open(slot, delivery_date, now=now):
        raise SlotClosed(f"Ordering for {slot.label.lower()} has closed.")

    lines, subtotal = price_lines(requested, delivery_date=delivery_date, slot=slot)

    snapshot = address_snapshot or (address.as_snapshot() if address else None)
    if not snapshot or not snapshot.get("pincode"):
        raise NotServiceable("A delivery address is required.")

    zones = zones_for_pincode(snapshot["pincode"], slot_key=slot.key)
    if not zones:
        raise NotServiceable(f"We don't deliver to {snapshot['pincode']} yet.")
    zone = next((z for z in zones if z.area_name == snapshot.get("area")), zones[0])

    if subtotal < zone.min_order:
        raise BelowMinimum(zone.min_order - subtotal, zone.min_order)

    snapshot = {**snapshot, "area": zone.area_name}
    delivery_fee = zone.delivery_fee
    total = subtotal + delivery_fee

    # order_no carries a random suffix, so a collision is possible but rare;
    # retry rather than failing a customer's checkout over it.
    for _ in range(5):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    tenant=tenant,
                    order_no=generate_order_number(tenant, delivery_date),
                    customer=customer, channel=channel, source=source,
                    payment_mode=payment_mode,
                    slot=slot, delivery_date=delivery_date,
                    items=lines, address=snapshot,
                    subtotal=subtotal, delivery_fee=delivery_fee, total=total,
                )
            break
        except IntegrityError:
            continue
    else:
        raise OrderError("Could not allocate an order number. Please try again.")

    OrderEvent.objects.create(
        tenant=tenant, order=order, from_status="",
        to_status=OrderStatus.PLACED, actor=f"customer:{channel}",
    )
    return order


def advance_status(order: Order, to_status: str, *, actor: str, note: str = "") -> Order:
    """Move an order forward, or cancel it. Anything else is refused.

    Statuses never move backwards. A kitchen that has told a customer their
    food is out for delivery cannot quietly rewind to "preparing"."""
    if order.status == to_status:
        return order
    if order.is_terminal:
        raise InvalidTransition(f"{order.order_no} is already {order.get_status_display().lower()}.")
    if to_status != OrderStatus.CANCELLED and to_status not in STATUS_FLOW[order.status]:
        raise InvalidTransition(
            f"{order.order_no} cannot go from {order.status} to {to_status}."
        )

    previous = order.status
    order.status = to_status
    fields = ["status"]
    if to_status == OrderStatus.CANCELLED and note:
        order.cancelled_reason = note
        fields.append("cancelled_reason")
    order.save(update_fields=fields)

    OrderEvent.objects.create(
        tenant=order.tenant, order=order,
        from_status=previous, to_status=to_status, actor=actor, note=note,
    )
    return order
