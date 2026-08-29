"""The shopping cart.

Session-backed for now. Phase 4 gives WhatsApp a database-backed cart, and
this interface is what both will share — so order creation never learns which
channel it came from.
"""
from dataclasses import dataclass
from datetime import date as date_cls
from decimal import Decimal

from apps.catalog.models import MenuItem, Slot
from apps.catalog.services import resolve_menu
from apps.delivery.services import zones_for_pincode

SESSION_KEY = "cart"


@dataclass
class CartLine:
    item: MenuItem
    quantity: int
    unit_price: Decimal

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class Cart:
    """Reads and writes the session, but prices from the live menu.

    Prices are never trusted from the session — a stale price sitting in
    someone's browser must not decide what they pay.
    """

    def __init__(self, request):
        self.request = request
        self.session = request.session
        self._data = self.session.get(SESSION_KEY) or {}

    # -- state ------------------------------------------------------------

    @property
    def slot_key(self):
        return self._data.get("slot_key")

    @property
    def delivery_date(self):
        raw = self._data.get("delivery_date")
        return date_cls.fromisoformat(raw) if raw else None

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

    # -- mutation ---------------------------------------------------------

    def _save(self):
        self.session[SESSION_KEY] = self._data
        self.session.modified = True

    def set_context(self, slot_key: str, delivery_date: date_cls):
        """Switching slot or day empties the cart — a lunch item can't be
        carried into a dinner order."""
        if self.slot_key != slot_key or self.delivery_date != delivery_date:
            self._data = {
                "slot_key": slot_key,
                "delivery_date": delivery_date.isoformat(),
                "items": {},
                "pincode": self.pincode,
                "zone_id": self.zone_id,
            }
            self._save()

    def add(self, item_id: int, quantity: int = 1):
        items = self._data.setdefault("items", {})
        key = str(item_id)
        items[key] = max(0, items.get(key, 0) + quantity)
        if items[key] == 0:
            items.pop(key)
        self._save()

    def set_quantity(self, item_id: int, quantity: int):
        items = self._data.setdefault("items", {})
        key = str(item_id)
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
        self.session.pop(SESSION_KEY, None)
        self.session.modified = True

    # -- pricing ----------------------------------------------------------

    def lines(self):
        """Cart lines priced from today's menu, dropping anything no longer
        on sale. A sold-out dish silently leaving the cart is better than a
        customer paying for food the kitchen can't make."""
        if self.is_empty or not self.slot_key or not self.delivery_date:
            return []
        slot = Slot.objects.filter(key=self.slot_key).first()
        if slot is None:
            return []
        priced = {e.item.id: e for e in resolve_menu(self.delivery_date, slot)}

        lines, dropped = [], []
        for item_id_str, qty in list(self.items.items()):
            entry = priced.get(int(item_id_str))
            if entry is None:
                dropped.append(item_id_str)
                continue
            lines.append(CartLine(item=entry.item, quantity=qty, unit_price=entry.price))
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
