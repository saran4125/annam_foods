"""The shopping cart.

Session-backed for now. Phase 4 gives WhatsApp a database-backed cart, and
this interface is what both will share — so order creation never learns which
channel it came from.

Two rules guard the money here (`FIX-06`, `FIX-08`):

* Prices are never read from the session — a stale price in someone's browser
  must not decide what they pay. Every read re-prices from the live menu.
* The stored session shape is validated on load. Tampered, malformed or
  stale data degrades to an empty cart instead of throwing halfway through a
  page render.
"""
from dataclasses import dataclass
from datetime import date as date_cls
from decimal import Decimal

from apps.catalog.models import MenuItem, Slot
from apps.catalog.services import resolve_menu
from apps.delivery.services import zones_for_pincode

SESSION_KEY = "cart"
MAX_LINE_QUANTITY = 99

# A cart is one kind of order: a scheduled meal (one slot, one day) or a shop
# order of courier goods. They are priced and delivered differently, so they
# never share a cart -- exactly as orders.services.create_order requires.
MEAL = "meal"
COURIER = "courier"


@dataclass
class CartLine:
    item: object
    quantity: int
    unit_price: Decimal

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


def _tenant_key(request) -> str:
    """One cart per kitchen, even when two tenants share a browser cookie.

    The cart shipped namespaced by tenant id (`FIX-08`): a person ordering from
    two kitchens must never inherit the other kitchen's items from their
    session. Host-scoped cookies are a convenience, not an isolation control.
    """
    tenant = getattr(request, "tenant", None)
    if tenant is not None:
        return f"{SESSION_KEY}.{tenant.pk}"
    return SESSION_KEY


class Cart:
    """Reads and writes the session, but prices from the live menu."""

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self._key = _tenant_key(request)
        self._data = self._load_shape(self.session.get(self._key) or {})

    # -- state ------------------------------------------------------------

    @property
    def kind(self):
        return self._data.get("kind")

    @property
    def is_courier(self) -> bool:
        return self.kind == COURIER

    @property
    def slot_key(self):
        return self._data.get("slot_key")

    @property
    def delivery_date(self):
        return self._data.get("delivery_date")

    @property
    def pincode(self):
        return self._data.get("pincode", "")

    @property
    def zone_id(self):
        return self._data.get("zone_id")

    @property
    def items(self) -> dict:
        return self._data.get("items", {})

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def count(self) -> int:
        return sum(self.items.values())

    # -- load guard -------------------------------------------------------

    def _load_shape(self, raw):
        """A hostile or stale session must not crash a page.

        Anything that fails its type check is dropped; what remains is a valid
        (possibly empty) cart. A malformed date is ignored, not trusted."""
        if not isinstance(raw, dict):
            return {}
        data = {}

        kind = raw.get("kind")
        data["kind"] = kind if kind in (MEAL, COURIER) else None

        slot_key = raw.get("slot_key")
        data["slot_key"] = slot_key if isinstance(slot_key, str) else None

        raw_date = raw.get("delivery_date")
        try:
            data["delivery_date"] = date_cls.fromisoformat(raw_date) if raw_date else None
        except (TypeError, ValueError):
            data["delivery_date"] = None

        items = {}
        raw_items = raw.get("items")
        if isinstance(raw_items, dict):
            for key, value in raw_items.items():
                try:
                    qty = int(value)
                except (TypeError, ValueError):
                    continue
                if not (1 <= qty <= MAX_LINE_QUANTITY):
                    continue
                try:
                    items[str(int(key))] = qty
                except (TypeError, ValueError):
                    continue
        data["items"] = items

        pincode = raw.get("pincode")
        data["pincode"] = pincode if isinstance(pincode, str) else ""

        zone_id = raw.get("zone_id")
        if isinstance(zone_id, int):
            data["zone_id"] = zone_id
        elif isinstance(zone_id, str) and zone_id.isdigit():
            data["zone_id"] = int(zone_id)
        else:
            data["zone_id"] = None

        return data

    # -- mutation ---------------------------------------------------------

    def _save(self):
        payload = {
            "kind": self._data.get("kind"),
            "slot_key": self._data.get("slot_key"),
            "delivery_date": self._data.get("delivery_date").isoformat()
            if self._data.get("delivery_date") else None,
            "items": self._data.get("items", {}),
            "pincode": self._data.get("pincode", ""),
            "zone_id": self._data.get("zone_id"),
        }
        self.session[self._key] = payload
        self.session.modified = True

    def set_context(self, slot_key: str, delivery_date: date_cls):
        """Adopt a delivery context.

        Called by the purchase service once an order is actually being built.
        Browsing the menu never calls this — reading a page must not delete a
        customer's cart (`FIX-05`)."""
        self._data["kind"] = MEAL
        self._data["slot_key"] = slot_key
        self._data["delivery_date"] = delivery_date
        self._data.setdefault("items", {})
        self._save()

    def set_courier(self):
        """Adopt the shop (courier goods) context: no slot, no delivery day."""
        self._data["kind"] = COURIER
        self._data["slot_key"] = None
        self._data["delivery_date"] = None
        self._data.setdefault("items", {})
        self._save()

    def add(self, item_id: int, delta: int):
        """Change one line's quantity by a bounded delta."""
        items = self._data.setdefault("items", {})
        key = str(item_id)
        qty = max(0, items.get(key, 0) + delta)
        if qty > MAX_LINE_QUANTITY:
            qty = MAX_LINE_QUANTITY
        if qty <= 0:
            items.pop(key, None)
        else:
            items[key] = qty
        self._save()

    def set_quantity(self, item_id: int, quantity: int):
        items = self._data.setdefault("items", {})
        key = str(item_id)
        quantity = min(max(quantity, 0), MAX_LINE_QUANTITY)
        if quantity <= 0:
            items.pop(key, None)
        else:
            items[key] = quantity
        self._save()

    def set_pincode(self, pincode: str, zone_id: int | None = None):
        self._data["pincode"] = pincode
        self._data["zone_id"] = zone_id
        self._save()

    def clear(self):
        self._data = {}
        self.session.pop(self._key, None)
        self.session.modified = True

    # -- pricing ----------------------------------------------------------

    def lines(self):
        """Cart lines priced from the live menu, dropping anything no longer
        on sale. A sold-out dish silently leaving the cart is better than a
        customer paying for food the kitchen can't make."""
        if self.is_empty:
            return []
        if self.is_courier:
            # Courier goods are priced straight from the live catalog.
            prices = {
                item.id: (item, item.price)
                for item in MenuItem.objects.filter(
                    pk__in=[int(k) for k in self.items], active=True, fulfilment="courier",
                )
            }
        else:
            if not self.slot_key or not self.delivery_date:
                return []
            slot = Slot.objects.filter(key=self.slot_key).first()
            if slot is None:
                return []
            prices = {e.item.id: (e.item, e.price) for e in resolve_menu(self.delivery_date, slot)}

        lines, dropped = [], []
        for item_id_str, qty in list(self.items.items()):
            found = prices.get(int(item_id_str))
            if found is None:
                dropped.append(item_id_str)
                continue
            lines.append(CartLine(item=found[0], quantity=qty, unit_price=found[1]))
        for item_id_str in dropped:
            self._data["items"].pop(item_id_str, None)
        if dropped:
            self._save()
        return lines

    @property
    def zone(self):
        if not self.pincode:
            return None
        zones = zones_for_pincode(self.pincode, slot_key=self.slot_key)
        if self.zone_id:
            for z in zones:
                if z.id == self.zone_id:
                    return z
        return zones[0] if len(zones) == 1 else None

    def totals(self):
        lines = self.lines()
        subtotal = sum((l.line_total for l in lines), Decimal("0"))
        zone = self.zone
        delivery_fee = zone.delivery_fee if zone else Decimal("0")
        min_order = zone.min_order if zone else Decimal("0")
        below_minimum = bool(zone) and subtotal < min_order
        return {
            "lines": lines,
            "subtotal": subtotal,
            "delivery_fee": delivery_fee,
            "min_order": min_order,
            "below_minimum": below_minimum,
            "shortfall": max(min_order - subtotal, Decimal("0")),
            "total": subtotal + delivery_fee,
            "zone": zone,
        }