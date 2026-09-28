# Phase 4 — Owner backend

> **Superseded by [PLAN.md](PLAN.md) v2 (28 September 2026).** Kept as implementation detail; the owner backend is specified in PLAN.md §11 and built across Phases B and F (§17). Where this file and PLAN.md differ, PLAN.md wins.

## Goal

The kitchen owner runs his business here every morning without calling you.
This is the thing he pays ₹5,000/month for, so it has to be *fast*, not
merely complete. The daily loop is: look at today's orders, turn off what's
sold out, add tomorrow's specials. Two minutes.

This is **not** Django admin. Django admin is the SEER super admin (Phase 6).
The owner gets a purpose-built area at `/manage/`.

---

## Access

- Login by `TenantUser` for the tenant the hostname resolved to
- A user with no `TenantUser` row for this tenant gets 403, not a redirect loop
- `role`: `owner` sees everything; `manager` everything but settings and staff;
  `staff` sees only Today and Orders
- **`tenant.backend_is_read_only`** (the `restricted` rung) blocks every write
  except billing, and shows a banner explaining why. Reads still work — he can
  see his orders and take money, he just can't edit the menu. Enforce this in
  one decorator, not per view.
- `tenant.shows_billing_banner` renders a pay-now banner on every page

---

## Screens

### Today — `/manage/`
The default landing page.
- Live order feed, newest first, with an audible alert on arrival
- Counts by slot; today's revenue; unpaid orders
- One-tap status advance on each row
- Polling is fine (HTMX `hx-trigger="every 15s"`); do not add websockets

### Orders — `/manage/orders/`
- Filter by date range, slot, channel, status, payment status
- Detail view with the full `OrderEvent` timeline
- Download or print the invoice
- Mark cash collected (for `cod_pending`)
- Record a refund — write the row, don't automate the Razorpay call yet

### Menu — `/manage/menu/`
The screen that gets used daily. Get this one right.

Renders one of two editors from `TenantConfig.menu_mode`:

- **daily** — a day view: date picker, one column per slot, every item with an
  availability toggle, a quantity limit and an optional price override.
  Writes `MenuSchedule` rows with `mode="date"`.
- **weekly** — a 7×slots grid of the standing template. Writes rows with
  `mode="weekday"`.

Both must offer:
- **Copy yesterday** / **copy last week** — one click, the single biggest
  time-saver for a kitchen
- **Mark sold out** — sets `qty_limit = qty_sold`, takes the dish off the live
  menu immediately
- A visible marker when a dated row is overriding the weekly template, with a
  one-click revert. A weekly kitchen must be able to see *why* today differs
  from the template.

Item management (create, edit, price, photo, category) lives here too.

### Zones — `/manage/zones/`
Pincode, area, delivery fee, minimum order, which slots. Inline editing;
this table is short and changes rarely.

### Customers — `/manage/customers/`
Phone, order count, lifetime value, last order, notes. Search by phone.
Read-mostly.

### Pages — `/manage/pages/`
Markdown editor with a live preview for `content.Page`, plus banner management.
The owner writes his own festival offer and refund policy — this is what keeps
new pages out of a deploy.

### Settings — `/manage/settings/`
- Brand name, tagline, logo, theme colours (write to `TenantConfig.theme`)
- Kitchen hours, slots and their cutoffs
- Invoice details: prefix, GSTIN, FSSAI
- Staff logins

### Payments — `/manage/settings/payments/`
Follows the SeerDesk WhatsApp Settings pattern the owner already knows: paste
credentials, hit **Test Connection**, get a plain-language pass or fail, copy
the webhook URL to paste into Razorpay.

| Field | Behaviour |
|---|---|
| Razorpay Key ID | stored and displayed — not a secret |
| Key Secret | **write-only.** Show `••••••••4f2a`; replaceable, never read back |
| Webhook Secret | write-only, same |
| Test Connection | server-side call to Razorpay, reports authorised / rejected |
| Webhook URL | displayed with a copy button |
| Live / Test mode | toggle, so he can place a ₹1 test order first |

**Do not copy SeerDesk's eye-toggle for payment secrets.** That reveals the
stored value to the browser. A compromised owner login must not be able to walk
away with keys that move the client's money.

### Reports — `/manage/reports/`
Sales by day, slot, item and channel. CSV export. Keep it to aggregates over
`Order` — no separate reporting tables.

---

## Behaviours that must be tested

**Access**
- a user with no `TenantUser` for this tenant gets 403
- a `staff` user cannot reach Settings or Menu
- an owner of kitchen A cannot reach kitchen B's backend on B's hostname
- a `restricted` tenant: menu edit returns 403, order list still loads
- a `suspended` tenant: the owner can still log in, read orders and export

**Menu editor**
- toggling availability in daily mode writes a `mode="date"` row for that date
- toggling in weekly mode writes a `mode="weekday"` row
- "copy yesterday" reproduces yesterday's rows for today and nothing else
- "mark sold out" removes the dish from the storefront on the next request
- an override is shown as an override, and reverting removes the dated row and
  restores the template

**Orders**
- advancing status writes an `OrderEvent` with the acting user
- statuses cannot move backwards except to `cancelled`

---

## Out of scope

Rider assignment and delivery tracking; printed KOT tickets; inventory; any
analytics beyond the aggregates above.
