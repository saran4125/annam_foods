# Phase 3 — Orders, Razorpay, invoices

**Prerequisite: do `docs/phase-7-production.md` section 7a first.** Invoice
numbering needs `select_for_update()` and SQLite cannot provide it.

## Goal

A real customer can order from the website and pay, the kitchen is told, and
both parties get an invoice. This is the milestone where the product earns
money.

Web and WhatsApp must converge on **one order record** — `orders.channel` is
the only thing that differs. Build the service layer so Phase 5 adds a value to
that column and nothing else.

---

## Models — new app `apps/orders/`

All subclass `TenantOwnedModel`. All money is `Decimal`.

### `Customer`
```
phone         CharField(20), indexed
name          CharField(120), blank
email         EmailField, blank
source        CharField  web | whatsapp
first_seen    DateTimeField
last_seen     DateTimeField
notes         TextField, blank
unique_together: (tenant, phone)
```
Phone is the identity. No passwords — guest checkout with OTP.

### `Address`
```
customer      FK Customer, related_name="addresses"
label         CharField(40), blank      # Home, Office
line1, line2  CharField(200) / blank
landmark      CharField(120), blank
pincode       CharField(10)
zone          FK delivery.DeliveryZone, null      # resolved at save
is_default    BooleanField
```

### `Order`
```
order_no        CharField(24), unique per tenant   # see numbering below
customer        FK Customer
channel         CharField  web | whatsapp | manual
status          CharField  placed confirmed preparing out_for_delivery delivered cancelled
payment_status  CharField  pending paid failed refunded cod_pending
slot            FK catalog.Slot
delivery_date   DateField
items           JSONField      # snapshot, see below
address         JSONField      # snapshot
subtotal / delivery_fee / discount / total   Decimal
coupon_code     CharField(30), blank
placed_at       DateTimeField
cancelled_reason CharField(200), blank
```

`items` is a **snapshot**, not foreign keys:
```json
[{"item_id": 12, "name": "Veg Meals", "unit_price": "120.00",
  "quantity": 2, "line_total": "240.00", "is_veg": true}]
```
A price change next week must not rewrite last week's bill. Same for `address`.

### `OrderEvent`
```
order      FK Order, related_name="events"
from_status / to_status   CharField
actor      CharField(60)     # "customer", "owner:<user>", "razorpay", "system"
note       CharField(200), blank
at         DateTimeField
```
Append on every status change. This is the audit trail when a client asks what
happened to an order.

### `Payment`
```
order          FK Order
provider       CharField  razorpay
provider_ref   CharField(80), indexed   # razorpay payment id
event_id       CharField(80), blank, indexed   # webhook event id, for idempotency
method         CharField(30), blank
amount         Decimal
status         CharField  created captured failed refunded
raw            JSONField
at             DateTimeField
unique_together: (tenant, event_id) where event_id != ""
```

### `Invoice`
```
order            OneToOne Order
invoice_no       CharField(30)     # unique per tenant
pdf              FileField(upload_to="invoices/")
total            Decimal
issued_at        DateTimeField
sent_customer_at DateTimeField, null
sent_owner_at    DateTimeField, null
unique_together: (tenant, invoice_no)
```

Design the model for GST now — `gstin` and `fssai_no` already exist on
`TenantConfig`. Rendering them is Phase 6, but retrofitting a compliant invoice
series onto live data is genuinely painful.

---

## Services — `apps/orders/services.py`

```python
def create_order(*, customer, cart_lines, slot, delivery_date,
                 address, zone, channel) -> Order
```
The single entry point for both channels. Re-prices every line from
`catalog.services.resolve_menu` — **never trust prices from the caller**.
Validates: slot still open, zone serviceable, subtotal ≥ zone minimum, tenant
`can_take_orders`. Raises typed errors the callers can turn into messages.

```python
def allocate_invoice_number(tenant) -> str
```
```python
with transaction.atomic():
    config = TenantConfig.objects.select_for_update().get(tenant=tenant)
    number = f"{config.invoice_prefix}-{config.invoice_next_no:05d}"
    config.invoice_next_no += 1
    config.save(update_fields=["invoice_next_no"])
```
Sequential, no gaps, allocated under a row lock. In India a broken invoice
series is a compliance problem for your client, not an annoyance.

```python
def generate_order_number(tenant) -> str      # e.g. ANNAM-20260907-0041
def mark_paid(order, payment) -> Invoice      # transitions, invoices, notifies
def advance_status(order, to_status, actor) -> Order    # writes an OrderEvent
```

## Razorpay — `apps/payments/`

Keys are **per tenant**, already available on `tenant.secrets`
(`razorpay_key_id`, `razorpay_secret`, `razorpay_webhook_secret`,
`razorpay_live_mode`) — encrypted at rest and never returned to a browser.
`TenantSecrets` is built; do not create another credentials model.

```python
def create_payment_order(order) -> dict        # website: inline checkout
def create_payment_link(order) -> str          # WhatsApp: a link to send
def verify_webhook(tenant, body, signature) -> bool
```

### The webhook — `POST /api/webhooks/razorpay`

Must be **idempotent on Razorpay's event id**. Razorpay retries; a duplicate
delivery that burns a second invoice number breaks your client's invoice series.

```
1. resolve tenant (from the URL path or the payload's notes)
2. verify signature against that tenant's webhook secret — reject on mismatch
3. if Payment.objects.filter(event_id=…).exists(): return 200 immediately
4. inside transaction.atomic():
     write Payment, set order.payment_status=paid, append OrderEvent
     allocate invoice number, create Invoice row
5. queue: render PDF, then `messaging.services.queue(...)` for the customer's
   confirmation and invoice and the owner's alert, each with a `dedupe_key`
   derived from the event id so a redelivery cannot send twice
6. return 200
```

Do steps 1–4 synchronously and 5 on the queue. Razorpay wants a fast 200; the
customer's WhatsApp message can take an extra second.

## Invoice PDF

WeasyPrint, rendering a normal Django template. It's HTML and CSS you already
know. Store to `FileField`; local disk in dev, object storage in production.

---

## Routes

| Route | Purpose |
|---|---|
| `GET /checkout/` | phone + OTP, address, review |
| `POST /checkout/otp/` | request and verify OTP |
| `POST /checkout/place/` | create order, start payment |
| `GET /order/<order_no>/` | confirmation and live status |
| `GET /track/` | order number + phone lookup |
| `POST /api/webhooks/razorpay` | payment webhook, idempotent |
| `GET /invoice/<order_no>/` | download, owner or that customer only |

OTP in dev: log it to the console and accept any six digits behind a
`settings.OTP_DEBUG` flag. Don't wire an SMS provider yet — decide in Phase 6
whether OTP goes by SMS or WhatsApp, since the WABA makes the second cheaper.

## Owner-facing, minimum viable

Enough that the kitchen can work an order. Full backend is Phase 4.

- `GET /manage/orders/` — today's orders, filter by slot and status
- `POST /manage/orders/<id>/status/` — advance status, notify the customer
- Owner login via `TenantUser`; block if `tenant.backend_is_read_only`

---

## Behaviours that must be tested

**Order creation**
- an order created from a cart matches the cart's totals exactly
- prices come from the live menu, not from the caller — pass a wrong price and
  the order still uses the real one
- an order below the zone minimum is refused
- an order for a closed slot is refused
- an order for an unserviceable pincode is refused
- a suspended tenant cannot create an order
- `items` and `address` are snapshots — changing the item afterwards does not
  change the order

**Invoice numbering**
- numbers are sequential with no gaps
- two concurrent payments do not produce the same number (run it in threads
  against Postgres; this is the test that justifies 7a)
- numbering is per tenant — two kitchens both start at 1 and never collide

**Webhook**
- a valid signature marks the order paid and creates exactly one invoice
- an invalid signature changes nothing and returns 4xx
- **the same event delivered twice produces one Payment and one Invoice**
- a webhook for another tenant's order cannot touch this tenant's data

**Isolation**
- orders, invoices and customers do not leak between kitchens
- the invoice download refuses a customer who isn't on that order

---

## Out of scope

Cash on delivery beyond the `cod_pending` status existing; refunds through the
UI (record them, don't automate); rider assignment; GST rendering; coupons.
