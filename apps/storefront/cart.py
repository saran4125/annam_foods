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

# A delivery-date cart may combine Breakfast, Lunch and Snacks. Dinner stays
# separate. A Snacks-only courier cart has no scheduled delivery date.
MEAL = "meal"
COURIER = "courier"


@dataclass
class CartLine:
    item: object
    quantity: int
    unit_price: Decimal
    slot_key: str = ""
    line_key: str = ""

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

    @property
    def ordering_open(self):
        if self.is_courier:
            return True
        from apps.orders.services import price_combined_lines,OrderError
        try:
            price_combined_lines(self.requested_lines(),delivery_date=self.delivery_date,check_windows=True)
            return True
        except (OrderError,TypeError):
            return False

    @property
    def slot_keys(self):
        return sorted({self._data.get('line_slots', {}).get(k, self.slot_key or 'snacks') for k in self.items})

    def item_key(self, item_id, slot_key=None):
        slot_key = slot_key or self.slot_key or 'snacks'
        for key in self.items:
            if int(key.split(':')[-1]) == int(item_id) and self._data.get('line_slots', {}).get(key, self.slot_key or 'snacks') == slot_key:
                return key
        plain = str(item_id)
        return plain if plain not in self.items else f'{slot_key}:{item_id}'

    def requested_lines(self):
        from apps.orders.services import RequestedLine
        return [RequestedLine(int(k.split(':')[-1]), qty, self._data.get('line_slots', {}).get(k, self.slot_key or 'snacks')) for k, qty in self.items.items()]

    def quantities_for(self, slot_key):
        return {str(line.item_id): line.quantity for line in self.requested_lines() if line.slot_key == slot_key}

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
                    parts = str(key).split(':')
                    if len(parts)>2 or (len(parts)==2 and parts[0] not in ('breakfast','lunch','dinner','snacks')):
                        continue
                    cleaned = (parts[0]+':' if len(parts)==2 else '') + str(int(parts[-1]))
                    items[cleaned] = qty
                except (TypeError, ValueError):
                    continue
        data["items"] = items
        raw_slots = raw.get('line_slots') or {}
        data['line_slots'] = {k:v for k,v in raw_slots.items() if k in items and v in ('breakfast','lunch','dinner','snacks')} if isinstance(raw_slots,dict) else {}

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
            "line_slots": self._data.get("line_slots", {}),
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

    def add(self, item_id: int, delta: int, slot_key=None):
        """Change one line's quantity by a bounded delta."""
        items = self._data.setdefault("items", {})
        key = self.item_key(item_id, slot_key)
        self._data.setdefault("line_slots", {})[key] = slot_key or self.slot_key or "snacks"
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
        from apps.orders.services import price_combined_lines, price_courier_lines, OrderError
        from apps.catalog.models import MenuItem
        priced = []
        dropped = []
        for key, qty in list(self.items.items()):
            want = next(w for w in self.requested_lines() if self.item_key(w.item_id,w.slot_key)==key)
            try:
                if self.is_courier:
                    rows, _ = price_courier_lines([want])
                else:
                    rows, _ = price_combined_lines([want], delivery_date=self.delivery_date)
                row = rows[0]
                item = MenuItem.objects.get(pk=want.item_id)
                priced.append(CartLine(item,qty,Decimal(row['unit_price']),want.slot_key,key))
            except (OrderError, MenuItem.DoesNotExist):
                dropped.append(key)
        for key in dropped:
            self._data['items'].pop(key,None)
        if dropped:
            self._save()
        return priced

    @property
    def zone(self):
        from apps.delivery.policies import snacks_delivery_quote, eligible_zones
        from apps.orders.services import OrderError
        if self.is_courier:
            try:
                return snacks_delivery_quote(self.request.tenant, {'pincode':self.pincode,'zone_id':self.zone_id})
            except OrderError:
                return None
        if not self.pincode:
            return None
        zones = eligible_zones(self.pincode,self.slot_keys)
        if self.zone_id:
            return next((z for z in zones if z.pk==self.zone_id),None)
        return zones[0] if len(zones)==1 else None

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