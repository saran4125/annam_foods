# SeerKitchen — Master Plan

**Version 2 · 28 September 2026 · the single source of truth**

This is the complete plan: what we are building, why, how it is customised per
kitchen, exactly how WhatsApp behaves, how bills and payments work, and the
order to build it in. It replaces the earlier `PLAN.md`. The phase files,
`CODEBASE_STATUS.md`, `OPENCODE_STOREFRONT_HANDOFF.md` and
`storefront-redesign.md` remain as supporting detail — **where any of them
disagree with this document, this document wins.**

Coding conventions and the invariants no change may break live in
[`../AGENTS.md`](../AGENTS.md). Read that before writing code.

---

## Contents

1. [The outcome Hari asked for](#1-the-outcome-hari-asked-for)
2. [The product](#2-the-product)
3. [The business](#3-the-business)
4. [Where the code is today](#4-where-the-code-is-today)
5. [Architecture](#5-architecture)
6. [Plug and play — the customisation model](#6-plug-and-play--the-customisation-model)
7. [WhatsApp — the complete specification](#7-whatsapp--the-complete-specification)
8. [Invoicing — Annam's main concern](#8-invoicing--annams-main-concern)
9. [Payments](#9-payments)
10. [Storefront](#10-storefront)
11. [Owner backend](#11-owner-backend)
12. [Platform — super admin, onboarding, subscriptions](#12-platform--super-admin-onboarding-subscriptions)
13. [Data model](#13-data-model)
14. [Service layer and integration contracts](#14-service-layer-and-integration-contracts)
15. [Security, privacy and compliance](#15-security-privacy-and-compliance)
16. [Hosting and operations](#16-hosting-and-operations)
17. [Build phases](#17-build-phases)
18. [Testing rules](#18-testing-rules)
19. [Moving Annam across](#19-moving-annam-across)
20. [Risks and traps](#20-risks-and-traps)
21. [Open decisions](#21-open-decisions)
22. [Appendices](#22-appendices)

---

## 1. The outcome Hari asked for

Every requirement stated across the planning conversations, and where this
plan satisfies it. If a requirement is not in this table, it was not asked for;
if it is in the table, the linked section must deliver it.

| # | Requirement, in Hari's terms | Where |
|---|---|---|
| R1 | A complete pack for a cloud kitchen: a website the owner logs into to update the menu, checkout on the website, and ordering on WhatsApp too | §2, §9, §10, §11 |
| R2 | Website and WhatsApp interlinked — a website checkout sends the bill on WhatsApp; WhatsApp orders are tracked in the same billing | §5.4, §7.9, §8 |
| R3 | **Invoicing is the main concern.** Annam cannot issue invoices from its website or for orders that come from Meta's WhatsApp catalog. Customers must be able to request an invoice and get it from our app | §8 (whole section), §7.9 |
| R4 | Bills and payments sent on WhatsApp | §7.7, §7.9, §9 |
| R5 | Order updates on WhatsApp — everything | §7.8 |
| R6 | All the WhatsApp features already discussed, behaving similar/identical to Annam's current bot — not deviated | §7.3 parity table |
| R7 | Invoice and bill shared with both the owner and the customer | §8.7, §7.10 |
| R8 | Plug and play; when a kitchen needs customisation it must be easy | §6 |
| R9 | Cloud kitchens only; one common solution, duplicated and customised per client | §2.3, §6 |
| R10 | Home, menu, festival-offer page, delivery-cashback and refund-policy pages; owner edits them | §10, §11 |
| R11 | Menu planned daily or weekly — generic | §10.4 (built) |
| R12 | WhatsApp configuration and Razorpay configuration in the owner login, like SeerDesk | §11.9 |
| R13 | Super admin; switch a kitchen off if it stops paying ₹5,000/month | §12.4 |
| R14 | Setup ₹5–8k, ₹5,000/month; infrastructure ≤ ₹2,000/month for 20 clients | §3 |
| R15 | Python app; the app owns the logic; n8n at most a message driver | §5.1, §5.5 |
| R16 | Storefront UI/UX like sweetkaramcoffee.in, kitchen model like Annam, Annam's photographs | §10.1 |
| R17 | Image-only hero, three independently managed hero images, owner edits banners and the store (given to OpenCode) | §10.3, §11.7 |

---

## 2. The product

### 2.1 The problem

Annam Foods runs two disconnected halves. A website bought from another
provider, where the menu is typed in by hand and customers order. And a
WhatsApp bot that shows the menu, checks a pincode, and then **hands the
customer off** — to that website, or to Meta's WhatsApp catalog. Neither half
knows about the other. Nothing produces a bill.

That last point is the pain Annam feels most. A customer who orders through the
WhatsApp catalog and later asks for a GST bill for their office claim gets
nothing, because no system in the chain can make one.

### 2.2 What SeerKitchen is

One system per kitchen, underneath both channels:

- **A storefront** on the kitchen's own domain — shop-style, photograph-led,
  with a real cart and checkout.
- **A WhatsApp assistant** that behaves like the bot customers already know,
  but finishes the job: it takes the order, collects payment, and sends the
  bill.
- **One order book.** A website order and a WhatsApp order are the same record
  with a different `channel`. Same numbering, same bill series, same reports.
- **A billing engine** that can produce a correct bill for *any* order — web,
  WhatsApp chat, WhatsApp catalog, or one the owner types in because it came
  over the phone.
- **An owner backend** where the kitchen runs its day without calling anyone.

### 2.3 Scope

Cloud kitchens only: meal slots with order cutoffs, a menu that changes daily
or weekly, pincode-gated delivery, and courier-shipped items (snacks, sweets,
festival specials). Not dine-in, not table service, not general e-commerce.

The narrowness is what makes plug-and-play possible — slots, zones and daily
menus can be *assumed* and configured, instead of built per client.

---

## 3. The business

| | |
|---|---|
| Setup fee | ₹5,000–8,000 one-time, excluding domain |
| Recurring | ₹5,000 / month per kitchen |
| Target | ~20 kitchens |
| Infrastructure ceiling | ≤ ₹2,000 / month, all clients together |

**The client pays directly** for their domain, their WhatsApp Business account
(and therefore every WhatsApp message), and their Razorpay account (and
therefore payment fees). Those are legally and financially theirs.

**SeerKitchen pays** for hosting: a Hetzner CX33 (4 vCPU, 8 GB, ≈₹880/month)
running everything, Cloudflare's free tier in front, object storage for images
and bills. About ₹1,000–1,250/month at 20 kitchens — roughly 1% of ₹1,00,000
recurring.

### 3.1 WhatsApp costs change on 1 October 2026

From 1 October 2026 Meta bills two things that used to be free: **replies sent
inside the 24-hour customer-service window** and **utility templates sent
inside that window**, both at the market's utility rate. Inbound messages stay
free. This lands on each client's WABA bill, not ours, but it changes design:

- every bot step is one interactive message, never a text followed by buttons;
- optional updates (e.g. "preparing") are per-kitchen toggles, off by default;
- the owner backend shows messages sent and an estimated cost per month (§11.10),
  computed from `OutboundMessage`, so the client is never surprised.

### 3.2 The real cost is support hours

Twenty kitchens means twenty owners messaging SEER when something looks wrong
at 6am. Plug-and-play (§6) is as much about bounding support as about speed of
onboarding: the owner must be able to change anything they are likely to want
changed without a developer.

---

## 4. Where the code is today

Repository: `~/Desktop/SEER/CloudKitchen` · Django 5.2 · **Phase A implemented locally**.
The pre-Phase-A baseline was 164 green tests. The PostgreSQL suite now has
189 green tests, including the Phase A foundation checks below.

| Area | State |
|---|---|
| Tenancy: tenants, domains, config, users, fail-closed scoping, hostname routing | **built** |
| `TenantSecrets` — WhatsApp and Razorpay credentials, Fernet-encrypted, write-only form | **built** |
| Catalog: slots with cutoffs, categories, items, `MenuSchedule` (daily and weekly from one table) | **built** |
| Delivery zones, pincode normalisation and serviceability | **built** |
| Content: owner pages (markdown), banners | **built** |
| Storefront: home, menu (product grid), session cart re-priced from the live menu, pincode check | **built** |
| Purchase service with typed outcomes, open-redirect guard, per-tenant cart namespacing | **built** |
| Messaging spine: `OutboundMessage` queue, retries, dedupe keys, Meta-limit validation, senders `meta_cloud` / `n8n` / `console` | **built** |
| `import_menu_images` command | **built** |
| Orders: customers, addresses, orders (snapshotted lines), status flow, event trail | **built** |
| PostgreSQL, background worker, scheduler | **built in Phase A** |
| Invoicing | Phase B started locally: tenant-scoped invoice models, number sequences, tax snapshot issuance, credit notes and bill requests; PDF delivery and owner/WhatsApp workflows remain |
| Payments | not built |
| WhatsApp inbound, conversation, catalog orders | not built |
| Owner backend | not built |
| Checkout, OTP | not built |
| Hero campaigns, categories/collections pages, owner CMS | partial |
| Subscriptions, suspension automation, onboarding kit | partial (status model and admin actions only) |
| Production deployment | not built |

### 4.1 Known defects to fix early (from review)

| Ref | Defect | Fix in |
|---|---|---|
| D1 | Tenant timezone is stored but never activated per request; cutoffs silently use the server zone | The existing middleware already activated it; Phase A now restores a prior active timezone too |
| D2 | Prices render with `floatformat:0`, which rounds ₹120.50 to ₹121 | Fixed in Phase A with the money filter |
| D3 | Tests that derive times from the wall clock fail after 21:00 IST (one fixed; rule in §18) | Fixed the remaining shared-browser case in Phase A |
| D4 | Dev database lives in two places (`db.sqlite3` in the repo and `~/.seerkitchen/`) | PostgreSQL is now authoritative; the populated SQLite file remains an untouched backup |
| D5 | Logo and showcase images load from Annam's old CDN; they disappear when the old site does | Phase E |
| D6 | Moving the project folder breaks `.venv` console scripts; use `uv run python -m pytest` | documented in AGENTS.md |

### 4.2 Parallel storefront preview

A separate WordPress Multisite/WooCommerce storefront prototype was built for
the Sweet Karam Coffee visual comparison and Annam catalog review. It serves
`annam.localhost:8090` with product photography and a native owner editor;
`demo.localhost:8090` demonstrates another brand and separate account. Its
catalog and carts are not connected to the Django order book, and checkout is
disabled. This is an architectural difference from §5, not a production
cutover. Decide whether to adopt WordPress or continue the Django storefront
before connecting any checkout or WhatsApp order flow; do not create two
authoritative order systems.

---

## 5. Architecture

### 5.1 Stack

| Layer | Choice |
|---|---|
| Application | Django 5, server-rendered templates + HTMX, no SPA |
| Database | PostgreSQL (SQLite only until Phase A) |
| Background work | django-q2 (or Huey) + Redis: message sends, PDF rendering, reminders, scheduled jobs |
| PDFs | WeasyPrint — a bill is an HTML template |
| Edge | Caddy with on-demand TLS — one certificate per client domain, automatically |
| WhatsApp | Meta Cloud API, per-client WABA |
| Payments | Razorpay, per-client account |
| Hosting | One Hetzner CX33, Docker Compose |

### 5.2 One codebase, one database, many kitchens

- Every request resolves a tenant from its hostname; every tenant-owned query
  is scoped and **fails closed** without a tenant (`TenantOwnedModel`).
- Everything that differs between kitchens is data (§6). No per-client code,
  no per-client branches.
- A guard test fails the build if any tenant-owned model skips scoping.

### 5.3 The shape of the system

```
                    ┌──────────── channels ────────────┐
  Customer ─ web ─▶ │ Storefront (Django templates)    │
  Customer ─ WA  ─▶ │ WhatsApp webhook  /wa/<slug>/…    │──┐
  Owner   ─ web ─▶  │ Owner backend     /manage/…      │  │
  Owner   ─ WA  ─▶  │ (same webhook, owner numbers)    │  │
  Meta catalog ──▶  │ (order messages on the webhook)  │  │
                    └──────────────────────────────────┘  │
                                                          ▼
          ┌──────────────────── services (plain Python) ─────────────────┐
          │ catalog.resolve_menu   delivery.zones_for_pincode             │
          │ orders.create_order    billing.issue_invoice                  │
          │ payments.request_payment   whatsapp.conversation.handle       │
          │ messaging.queue        notifications.on_order_event           │
          └───────────────────────────────────────────────────────────────┘
                    │                    │                    │
                PostgreSQL        worker + scheduler      adapters
                                                 ┌── WhatsApp senders (meta_cloud | n8n | console)
                                                 ├── payment providers (razorpay | manual)
                                                 └── extension hooks (webhooks to n8n, Sheets…)
```

### 5.4 One order book

Every way an order can arrive ends in the same function,
`orders.services.create_order()`. It re-prices every line from the live menu —
callers pass quantities, never prices — and records `channel` and `source`:

| channel | source | How it arrives |
|---|---|---|
| `web` | `storefront` | Website checkout |
| `whatsapp` | `wa_chat` | Guided ordering inside the chat (§7.5 A) |
| `whatsapp` | `wa_catalog` | Customer sends a cart from Meta's WhatsApp catalog (§7.5 B) |
| `manual` | `owner` | Owner types it in — phone orders, old-website orders, requests for a bill (§8.6) |

Because they are one record, every downstream thing — payment, bill,
WhatsApp updates, reports, the owner's order list — works identically for all
four.

### 5.5 The app owns every message; n8n is optional plumbing

Decided in [ADR 0001](adr/0001-messaging-architecture.md) and extended here to
the inbound side.

**Outbound** (built): services build a payload with `messaging.payloads`
(which enforces Meta's limits), queue it as an `OutboundMessage`, and a worker
delivers it through the tenant's chosen sender. A dead provider delays a
message; it never loses one.

**Inbound** (to build): two adapters, chosen per tenant.

| Adapter | Path | Use |
|---|---|---|
| `direct` (default) | Meta → `POST /wa/<slug>/webhook` | New kitchens; Annam after cutover |
| `relay` | Meta → n8n → `POST /wa/<slug>/relay` | Only if a client's Meta webhook must keep pointing at n8n |

Both verify, dedupe, log and hand the same normalised event to the same
handler. The relay must forward Meta's original body and
`X-Hub-Signature-256` header so the app still verifies Meta's signature.

**Legacy forwarding (migration only).** During Annam's transition the app is
the front door and forwards any event it does not yet handle to the old n8n
Discovery webhook (`TenantSecrets.legacy_forward_url`). Each feature moves into
the app by being handled instead of forwarded; when nothing is forwarded, the
setting is cleared and n8n is retired for Annam. See §19.

**Client-specific extras** (group tracking, Google Sheets logging, a bespoke
notification) are *extensions* (§6.5): the app emits signed event webhooks and
n8n may consume them. n8n never decides what a customer sees.

---

## 6. Plug and play — the customisation model

Plug and play means: **a new kitchen goes live in under an hour, and any change
a kitchen asks for later is made at the lowest level that can express it.**
Each level is cheaper and safer than the one below it. Skipping down a level
needs a reason written in the change.

| Level | Who changes it | Examples | Deploy? |
|---|---|---|---|
| 1. Owner settings | the kitchen owner, in `/manage/` | menu, prices, photos, slots and cutoffs, zones, pages, hero images, bot wording, keywords, COD on/off, credentials | no |
| 2. Feature flags | SEER, in the super admin | seasonal offers, catalog ordering, native WhatsApp Pay, owner WhatsApp commands, GST mode | no |
| 3. Presets | SEER, applied at provisioning | "daily meals", "snacks & sweets courier", "mixed" | no |
| 4. Theme overrides | SEER | a kitchen-specific storefront template | yes, isolated |
| 5. Extensions | SEER | event webhooks to n8n, Sheets export, group tracking | no (config) / once (new extension) |
| 6. Core change | SEER | something every kitchen benefits from — it becomes a flag | yes |

### 6.1 Level 1 — owner settings

Everything a kitchen changes weekly lives in the owner backend (§11). Bot
wording is data: every message the assistant sends is a **copy key** with a
default in code and an optional per-tenant override (`BotCopy`), so an owner
can change "Vanakkam! What would you like today?" without touching anything
else. Keywords that trigger flows (greetings, "bill", festival names) are
per-tenant lists with defaults.

### 6.2 Level 2 — feature flags

`TenantConfig.features` is a JSON field, but flags are declared in one
registry in code — name, type, default, description — and read only through
`tenant.feature("name")`. A missing key always means the registry default,
never "whatever the code happens to do".

| Flag | Default | Effect |
|---|---|---|
| `website_ordering` | on | storefront checkout |
| `whatsapp_chat_ordering` | on | guided ordering inside the chat |
| `whatsapp_catalog_ordering` | off | accept carts from Meta's catalog |
| `whatsapp_catalog_sync` | off | push menu and availability to Meta's catalog daily |
| `native_whatsapp_pay` | off | pay inside WhatsApp (`order_details`) instead of a link |
| `cod` | off | cash on delivery |
| `manual_payments` | on | owner may mark an order paid (UPI to owner, cash) |
| `snacks_courier` | off | courier-fulfilled items and the Snacks menu branch |
| `seasonal_offers` | off | seasonal collection, its menu button and keywords |
| `invoice_on_request` | on | customers can ask for a bill in chat |
| `owner_whatsapp_commands` | off | owner runs orders by WhatsApp (§7.10) |
| `notify_preparing` / `notify_confirmed` | off | optional status messages (cost) |
| `owner_copy_of_bill` | on | send each bill to the owner too |
| `reorder_prompt` | on | "Order again" after delivery |
| `language_ta` | off | Tamil copy alongside English |

### 6.3 Level 3 — presets

A preset is a data file (`presets/<name>.yaml`) applied by
`provision_tenant --preset <name>`: slots, default copy, flags, template pack,
theme tokens, sample pages (refund policy, delivery cashback, about). A new
*kind* of kitchen is a new preset file, never new code.

### 6.4 Level 4 — theme overrides

The template loader looks in `tenants/<slug>/templates/` before the defaults,
for **storefront presentation only**. Overrides are listed in the super admin
with the date they were added, because each one is something that must be
checked on every upgrade. Business logic may never be overridden this way.

### 6.5 Level 5 — extensions

A small registry of named hooks fired by the service layer —
`order.placed`, `order.paid`, `order.status_changed`, `invoice.issued`,
`invoice.requested`, `message.unmatched`, `customer.created`. An extension is
enabled per tenant with settings. First extensions:

| Extension | Does |
|---|---|
| `event_webhook` | POSTs signed JSON for chosen events to a URL (n8n, Zapier, the client's own system) |
| `sheets_export` | appends orders/bills to a Google Sheet |
| `group_tracking` | Annam's WhatsApp-group invite and join tracking (Green API) |

Extensions run from the worker. A failing extension never blocks an order.

### 6.6 Guardrails that keep it plug-and-play

- A test fails if any tenant slug (e.g. `"annam"`) appears in application code
  under `apps/`. Kitchen-specific behaviour is data.
- Every flag has a registry entry and a test for both states.
- Every copy key has a default; a tenant override may not introduce new
  template variables.
- Presets are validated by a test that provisions each one into an empty
  database and loads its storefront and first bot message.

### 6.7 New kitchen in under an hour

1. Super admin → **New kitchen**: name, slug, domain, owner phone and email,
   preset. Creates tenant, config, domain, owner login, default pages, slots,
   copy, and queues the template pack for Meta approval.
2. Client, in their own backend: pastes WABA credentials and Razorpay keys,
   presses **Test connection** for each (§11.9).
3. SEER points the client's domain at the server; Caddy issues the certificate.
4. Owner uploads the menu (CSV import or one by one) and photos
   (`import_menu_images` or upload).
5. SEER runs the go-live checklist: test order in test mode, bill generated and
   received on WhatsApp, owner alert received, templates approved.

---

## 7. WhatsApp — the complete specification

### 7.1 Principles

1. **Familiar first.** Annam's customers keep the assistant they already know —
   same greeting, same Food / Snacks / Seasonal buttons, same pincode and slot
   questions. What changes is that it now *finishes* the order instead of
   handing off. §7.3 lists every existing behaviour and what happens to it.
2. **The app decides; WhatsApp displays.** Conversation logic is plain Python in
   this repository with tests — not a visual flow in n8n. That is what produced
   Annam's 110-node workflow and its repeated breakages.
3. **The conversation is a pure function.** `handle(session, event, ctx)`
   returns the next state, the replies, and a list of *actions*
   (`CreateOrder`, `RequestPayment`, `IssueInvoice`, `NotifyOwner`, …). An
   executor performs the actions. The flow can therefore be tested as tables of
   input → output with no network and no database.
4. **One interactive message per step.** From 1 October 2026 every reply is
   billed (§3.1). No "text, then buttons" pairs.
5. **Nothing about money is taken from the chat.** Prices come from the menu;
   payment status comes from the payment provider, verified by lookup.

### 7.2 Inbound pipeline

```
POST /wa/<slug>/webhook   (or /relay)
  1. resolve tenant from slug                      unknown → 404
  2. verify X-Hub-Signature-256 with the app secret   bad → 401, nothing stored
  3. for each entry.changes[].value:
       statuses[]  → update OutboundMessage (sent / delivered / read / failed)
       messages[]  → normalise to InboundEvent, dedupe on wamid, store WaInboundMessage
  4. enqueue processing; return 200 immediately (Meta retries slow endpoints)

worker:
  InboundEvent → is it from an owner number?  → owner console (§7.10)
               → is the bot paused for this customer? → inbox only (§7.11)
               → conversation.handle(...) → replies + actions → executor
               → (migration) not handled and legacy_forward_url set → forward raw body
```

**Normalised event kinds:** `text`, `button` (reply id), `list` (row id),
`order` (catalog cart), `location`, `payment` (native WhatsApp Pay status),
`media` (image/document the customer sends — stored, acknowledged, flagged to
inbox), `unsupported`.

**Delivery failures after send.** A status webhook with error **131047**
(outside the 24-hour window) triggers one automatic retry as the mapped
template, if the message has one (§7.13). Any other async failure lands on the
`OutboundMessage` with its code, visible to the owner.

### 7.3 Parity with Annam's current bot

Everything the n8n bot does today, and what becomes of it. **Kept** means the
customer sees the same thing.

| # | Today (n8n) | In SeerKitchen |
|---|---|---|
| 1 | "hi / hello / hey / start / menu" at the start of a message (whole word) → 🍱 Food · 🍿 Snacks · 🎉 Seasonal buttons | **Kept.** Same buttons; Seasonal only while a seasonal collection is active |
| 2 | Seasonal offer toggle; off means nothing is shown or sent | **Kept** — `seasonal_offers` flag plus an active Collection with start/end dates |
| 3 | "Krishna Jeyanthi / jayanthi / jayenthi / janmashtami" (Tamil and English) jumps straight to the offer, whatever the conversation state | **Kept** — keywords are a per-collection list the owner edits; highest routing priority |
| 4 | Food → asks for pincode; returning customers skip it (saved pincode) | **Kept** |
| 5 | "600 106" accepted as 600106 | **Kept** (built) |
| 6 | Pincode with several areas → area list | **Kept** |
| 7 | Not serviceable → "sorry, not yet" + Snacks / Seasonal buttons | **Kept** |
| 8 | Change pincode button | **Kept** |
| 9 | Slot picker showing only open slots (no Sunday dinner) | **Kept** — driven by `MenuSchedule` and slot cutoffs |
| 10 | Menu shown, then "Order on website" or "View Catalog" hand-off | **Changed:** customers can now order *in the chat* (A below). Website and catalog buttons remain available per kitchen setting, and both now become real orders |
| 11 | Snacks → website or WhatsApp catalog choice | **Kept**, and with `snacks_courier` the Snacks menu can also be ordered in chat |
| 12 | Anything unrecognised → "didn't quite get that" + 📱 WhatsApp Us / 📋 Menu buttons | **Kept** |
| 13 | SUPPORT / HELP → support message | **Kept**, plus a real hand-off to a person (§7.11) |
| 14 | After an order between 21:00 and 04:00 → "Kitchen closed now! Your order will be confirmed by 4am" | **Kept** — window and wording are settings |
| 15 | "Order another slot?" after an order | **Kept** |
| 16 | Button labels within Meta's 20-character limit | **Enforced in code** (built) |
| 17 | Follow-up CRON | **Kept** as scheduled follow-ups: payment reminder, abandoned cart, reorder nudge — each opt-in and toggleable |
| 18 | 4 AM "today's menu is ready, please review" to the owner | **Kept** — owner morning summary (§7.10) |
| 19 | Daily scraper copying the menu from the old website | **Retired** — the menu lives in SeerKitchen; the scraper has nothing to scrape once the old site is gone |
| 20 | WhatsApp-group invite, join tracking (Green API), weekly group nudge | **Kept as an extension** (`group_tracking`) — not core |
| 21 | Portal inbox showing conversations | **Kept** — owner backend Inbox (§7.11) |
| 22 | — (planned, never built) Track my order | **Added** |
| 23 | — (planned, never built) Payment link, reminder at 20 min, expiry at 60 min | **Added** (§9) |
| 24 | — (planned, never built) New-order alert to the kitchen | **Added** |
| 25 | — (planned, never built) Preparing / out for delivery / delivered updates | **Added** (§7.8) |
| 26 | — Bills | **Added — the main concern** (§8) |

### 7.4 Conversation map

States (stored on `WaSession`, which resets to `IDLE` after 12 idle hours —
configurable):

```
IDLE ─greeting/unmatched-greeting→ MAIN_MENU
MAIN_MENU ─Food→ (pincode known? → SLOT : ASK_PINCODE)
          ─Snacks→ SNACKS (courier menu, no pincode)
          ─Seasonal→ SEASONAL (collection menu)
          ─My orders / Bill→ ORDERS
ASK_PINCODE → (several areas? ASK_AREA) → SLOT        not served → NOT_SERVED
SLOT → BROWSING (menu list for slot+date)
BROWSING ⇄ QUANTITY → CART_REVIEW ─Add more→ BROWSING
CART_REVIEW ─Checkout→ ADDRESS → SUMMARY
SUMMARY ─Confirm→ PAYMENT_CHOICE (online / COD) → AWAITING_PAYMENT
AWAITING_PAYMENT ─paid→ IDLE (confirmation + bill sent)
ORDERS → pick order → (bill sent / status shown / GST details / not listed → INVOICE_REQUEST)
any state ─seasonal keyword→ SEASONAL        ─"menu"/greeting→ MAIN_MENU
any state ─support/help→ HANDOFF (bot paused for this customer)
any state ─unmatched text→ CONTACT_FALLBACK (same buttons as today)
```

**Routing priority** (first match wins, same as today's `Route by State`):
1. owner number → owner console · 2. bot paused → inbox ·
3. interactive reply ids · 4. seasonal keywords · 5. bill/invoice keywords ·
6. support keywords · 7. greeting at message start (`^(hi|hello|hey|start|menu)\b`) ·
8. state-expected input (pincode, quantity, address) · 9. contact fallback.

### 7.5 Three ways to order on WhatsApp

All three end in `orders.services.create_order()`.

**A. Guided ordering in the chat** (`whatsapp_chat_ordering`, default on)

1. Slot list shows open slots only, with cutoff times.
2. Menu arrives as a list message — up to 10 rows per message (Meta's limit);
   a "More dishes" row pages through longer menus. Each row: name · ₹price ·
   veg/non-veg.
3. Picking a dish asks quantity with buttons **1 · 2 · 3** (typing a number
   also works).
4. Cart review: lines, subtotal, delivery fee, minimum-order status; buttons
   **Add more · Checkout · Clear**.
5. Address: the saved default (confirm with one tap), or a new one — house
   and street as text, or **share location** (stored as coordinates for the
   rider).
6. Summary: items, fee, total, delivery window; **Confirm · Change · Cancel**.
7. Payment: **Pay now** (link or native, §9) and, if enabled, **Cash on
   delivery**.

**B. Meta catalog cart** (`whatsapp_catalog_ordering`, Annam today)

Customers browsing the WhatsApp catalog send a cart. Meta delivers it as an
`order` message: `catalog_id`, `product_items[] {product_retailer_id,
quantity, item_price, currency}`, optional `text`.

- Map `product_retailer_id` → `MenuItem.retailer_id`. An unknown id is not
  guessed at: the customer is told that item can't be ordered right now and the
  owner is alerted.
- **Re-price from our menu.** `item_price` is what the customer saw, not what
  they owe. If it differs, the summary shows the current price, marked
  "price updated".
- A catalog cart has no slot or date. If exactly one slot is open, it is
  assumed and stated in the summary; otherwise the customer picks from the open
  slots. Courier items skip this.
- Pincode and address are then asked exactly as in A, and the flow joins A at
  **Summary**.

This is how catalog orders — invisible to any system today — become real
orders with payment and a bill.

**C. Website hand-off** (per-kitchen setting)

A `cta_url` button to the storefront carrying a signed, short-lived token that
identifies the WhatsApp number, so the web order is linked to the same
customer and its bill and updates come back on WhatsApp.

### 7.6 Catalog sync (`whatsapp_catalog_sync`)

The menu lives in SeerKitchen; Meta's catalog becomes a mirror of it.

- `MenuItem.retailer_id` is the SKU shared with Meta.
- On any menu change, and every day at 04:00 kitchen time, a job pushes name,
  description, price, image and **today's availability** (in stock only if on
  today's resolved menu) to the tenant's catalog via the Catalog API batch
  endpoint.
- Result per item is recorded; failures surface in the owner backend.

Without sync, the catalog and the menu drift — which is why catalog orders are
always re-priced (B above) whether sync is on or not.

### 7.7 Payments on WhatsApp

| Method | When | How |
|---|---|---|
| **Payment link** (default) | always available with Razorpay | Razorpay Payment Link, sent as a `cta_url` button "Pay ₹260" |
| **Native WhatsApp Pay** | `native_whatsapp_pay` on, gateway linked in Meta Business Suite | `interactive.order_details` message — customer pays by UPI or card without leaving WhatsApp |
| **Cash on delivery** | `cod` on | order confirmed as `cod_pending`; bill issued on delivery |
| **Paid to the owner directly** | `manual_payments` on | owner marks paid (UPI reference optional) in the backend or by WhatsApp command |

Native WhatsApp Pay in India works through Razorpay, PayU, BillDesk or Zaakpay.
The business sends `order_details` with `reference_id` (≤ 35 characters — our
order number), `type: physical-goods`, `payment_settings` naming the
configured gateway, `currency: INR`, and amounts as value × 100 with
offset 100. Status arrives on a `payment` webhook, **but Meta states it must
not be relied on alone** — the app confirms with a payment lookup before
marking anything paid. UPI is capped at ₹5,00,000 per transaction.

Reminders: at 20 minutes unpaid, one reminder with the same pay button; at 60
minutes the link expires and the order is cancelled with an **Order again**
button. Both times are settings.

### 7.8 Order updates on WhatsApp

Every order event produces at most one message. Inside the 24-hour window it is
a free-form interactive message; outside, the mapped template (§7.13).

| Event | Message | Default |
|---|---|---|
| Order placed, awaiting payment | summary + pay button | on |
| Payment reminder (20 min) | "Your order is waiting" + pay button | on |
| Payment expired (60 min) | cancelled + Order again | on |
| **Paid** | confirmation **with the bill attached** (§7.9) | on |
| Kitchen closed window | "Kitchen closed now — confirmed by 4am" (Annam wording) | on |
| Confirmed by kitchen | "Accepted" | off |
| Preparing | "Being prepared" | off |
| Out for delivery | with rider name/phone if entered | on |
| Delivered | thanks + **Order again** (+ bill for COD) | on |
| Cancelled | reason, refund note, credit note attached if a bill existed | on |
| Refund processed | amount and reference | on |

Orders paid through native WhatsApp Pay also receive Meta's `order_status`
message, mapped: confirmed/preparing → `processing`, out for delivery →
`shipped`, delivered → `completed`, cancelled → `canceled`.

Each message is queued with a dedupe key `order:<id>:<event>`, so a retried
job or a redelivered webhook can never send it twice.

### 7.9 Bills on WhatsApp

The billing engine is §8. On WhatsApp:

- **Automatically:** when a bill is issued, the PDF is uploaded through Meta's
  media endpoint and sent as a `document` message — filename
  `Bill-AF-26-27-00012.pdf`, caption "Bill for order ANNAM-20260907-4812 ·
  ₹260". A copy goes to the owner if `owner_copy_of_bill` is on.
- **On request, any time:** the customer types *bill*, *invoice*, *receipt*,
  *GST bill* (and Tamil equivalents the kitchen adds), taps **Get bill** under
  any order message, or picks **My orders**. The flow is in §8.8.

Sending through the media endpoint rather than a public link keeps bills
private; the storefront download (§10.2, §10.6) uses a signed, expiring URL.

### 7.10 The owner on WhatsApp

Owner numbers are listed in the kitchen's settings. Messages from them never
enter the customer flow.

**Alerts** (always): new paid order (items, slot, address, total, payment
mode); new COD order; bill request needing the owner (§8.8); catalog item that
couldn't be mapped; payment failure; WhatsApp or Razorpay credentials failing.

**Morning summary** (04:00, replaces Annam's "menu ready" message): today's
orders per slot so far, anything sold out, a link to the menu editor.

**Commands** (`owner_whatsapp_commands`) — for owners who live in WhatsApp, not
a browser. Every command replies with what it did.

| Command | Does |
|---|---|
| `ORDERS` | today's orders by slot with status |
| `READY 4812` / `OUT 4812` / `DONE 4812` | advance status (preparing / out for delivery / delivered) |
| `PAID 4812 [UTR]` | mark a manually paid order paid → bill issued and sent |
| `BILL 4812` | resend the bill to customer and owner |
| `SOLDOUT idly` | take a dish off today's menu |
| `CANCEL 4812 reason` | cancel; credit note if billed |

The last four digits of the order number are enough when unambiguous for
today; otherwise the reply asks which.

### 7.11 Handing over to a person

**Support**, **Talk to us**, or the owner pressing **Take over** in the inbox
pauses the bot for that customer (`bot_paused_until`, default 2 hours). The
owner replies from the backend **Inbox** — conversation list, full history of
inbound and outbound messages, a reply box (free-form inside the 24-hour
window; template picker outside it), **Resume bot**. Customer messages during a
pause raise an unread badge and an owner alert.

### 7.12 Copy, keywords and language

- Every message the bot sends is a copy key (`menu.greeting`,
  `pincode.not_served`, `bill.caption`, …) with an English default in code, an
  optional Tamil default, and an optional per-tenant override edited in the
  owner backend (§11.8). Variables are fixed per key; overrides can't add new
  ones.
- Keyword lists per intent — greeting, support, bill, seasonal (per
  collection) — are per-tenant, with defaults.
- `language_ta`: customers are asked once ("English / தமிழ்"), the choice is
  stored on the customer, and copy resolves in that language with English as
  fallback.

### 7.13 Template pack

Messages outside the 24-hour window must be approved templates. Each kitchen
gets the same pack, submitted automatically on provisioning through the
WhatsApp Business Management API and tracked in `WaTemplate` (status,
rejection reason). The go-live checklist waits for approval.

| Template | Category | Used for |
|---|---|---|
| `order_confirmed` | Utility | paid order confirmation outside window |
| `payment_reminder` | Utility | reminder when window closed |
| `order_update` | Utility | out for delivery / delivered / cancelled (status as a variable) |
| `bill_ready` | Utility | bill delivered later (COD on delivery, requested bills) — document header |
| `refund_processed` | Utility | refunds |
| `otp_login` | Authentication | storefront checkout OTP |
| `reorder_nudge` | Marketing | opt-in only, off by default |
| `group_invite` | Marketing | `group_tracking` extension only |

Marketing templates are sent only to customers with a recorded opt-in.

### 7.14 Meta's hard limits (enforced in `messaging.payloads`)

| Limit | Value | Origin |
|---|---|---|
| `cta_url` button label | 20 characters | a 26-character label broke every "Place Order" tap at Annam for days |
| Reply buttons | 3 per message, 20 characters each | |
| List rows | 10 per message, row title 24 characters | |
| Body text | 1,024 characters | |
| URLs per message | one | why "website or catalog" is a choice, not two links |
| `order_details.reference_id` | 35 characters | native payments |
| UPI via WhatsApp Pay | ₹5,00,000 per transaction | native payments |

Violations raise while the message is being built — never at send time.

---

## 8. Invoicing — Annam's main concern

### 8.1 What is broken today

Annam has three ways customers buy, and **none of them can produce a bill**:

| How the customer ordered | Who could bill it today |
|---|---|
| Annam's current website (third-party provider) | nobody — the provider doesn't issue invoices |
| WhatsApp catalog cart (Meta) | nobody — the cart arrives as a chat message and no system turns it into an order |
| Phone call / direct WhatsApp chat with the owner | nobody — written on paper, if at all |

Customers who need a bill — office meal claims, corporate lunches, anyone
wanting a GST invoice — are turned away or handed something hand-written.

### 8.2 The rule

**SeerKitchen can issue a correct bill for any order, however it was placed,
and deliver it on WhatsApp.** Orders placed through SeerKitchen are billed
automatically. Orders placed anywhere else can be entered by the owner in under
a minute and billed the same way. A customer can always ask for their bill in
the chat.

This is the first thing to ship (Phase B, §17). It solves Annam's problem while
the old website and the old n8n bot are still running.

### 8.3 Three tax modes — set per kitchen

Which document a kitchen may issue depends on its GST position. That is a fact
about the client's business which **their accountant must confirm**; SeerKitchen
supports all three and never assumes.

| `gst_mode` | Document title | Tax shown | Required declaration |
|---|---|---|---|
| `regular` | **Tax Invoice** | CGST + SGST (intra-state) or IGST (inter-state) at the configured rate | — |
| `composition` | **Bill of Supply** | none | "Composition taxable person, not eligible to collect tax on supplies" |
| `unregistered` | **Bill** | none | — |

Research notes for the accountant conversation (not advice): restaurant
services including cloud kitchens are commonly taxed at **5% without input tax
credit**, SAC **996331**; composition is available up to ₹1.5 crore turnover
for kitchens selling directly, and is lost by selling through Swiggy/Zomato;
orders placed through those platforms are billed by the platform itself under
section 9(5), so the kitchen must **not** bill them again. Rate, SAC and mode
are settings, defaulting to 5% / 996331 / `unregistered` until confirmed.

### 8.4 What every bill carries

From CGST Rule 46, plus the FSSAI requirement that has applied to food
businesses since 1 October 2021:

- Seller: legal name, address, **GSTIN** (regular/composition), **FSSAI
  licence or registration number** (always — mandatory on bills, receipts and
  cash memos).
- Serial number (§8.5) and date of issue.
- Buyer: name and phone always; **GSTIN, name and billing address when the
  buyer is registered**; address for an unregistered buyer when the value is
  ₹50,000 or more, or when they ask for it.
- Place of supply with state name and code; delivery address.
- Per line: description, SAC, quantity, unit price, taxable value, tax rate,
  tax amount.
- Delivery fee as a line (treatment in §8.10).
- Totals: taxable value, CGST, SGST or IGST, round-off, grand total, **amount in
  words** (Indian numbering: lakh, crore).
- Payment mode and reference (Razorpay id, UTR, "Cash on delivery").
- Order number, channel ("Ordered on WhatsApp"), slot and delivery date.
- Authorised-signatory line; footer text set by the kitchen.

The seller and buyer details are **snapshotted onto the bill** when it is
issued. Changing the kitchen's address next year must not rewrite this year's
bills.

### 8.5 Numbering

Rule 46 requires a consecutive serial number of **at most 16 characters**, using
letters, digits, hyphen and slash, **unique within a financial year**.

- Format setting, default `{prefix}/{fy}/{seq}` → `AF/26-27/00012`
  (14 characters). `fy` is April–March. `seq` is zero-padded.
- On save of the setting, the worst-case length (sequence at its padded width)
  is computed and anything over 16 characters, or using other characters, is
  rejected with a message saying why.
- **Gapless.** Numbers come from `InvoiceSequence (tenant, series, fy)`,
  incremented under `SELECT … FOR UPDATE` in the same transaction that creates
  the bill. If the transaction rolls back, the number is not consumed.
  **This needs PostgreSQL** — which is why Phase A precedes billing.
- A new financial year starts a new sequence at 1 automatically.
- Credit notes have their own series (`{prefix}C/{fy}/{seq}`).
- Order numbers (`ANNAM-20260907-4812`) are *references*, not bill numbers, and
  may have gaps.

### 8.6 When a bill is made — seven ways

| # | Trigger | Bill issued when |
|---|---|---|
| 1 | Online payment captured (web or WhatsApp) | immediately on verified payment |
| 2 | Cash on delivery | on **Delivered**, or when the owner records cash collected |
| 3 | Owner marks a manual payment (UPI to owner, cash at counter) | on marking paid |
| 4 | Customer asks in the chat for a listed order (§8.8) | immediately, if the order is eligible; otherwise told when |
| 5 | Customer asks for an order the system doesn't know (§8.8) | when the owner completes the request |
| 6 | Owner's **Quick bill** — for phone orders or old-website orders | on save |
| 7 | Customer downloads from the storefront order page | the existing bill; never a new one |

"Eligible" means paid, or COD and delivered. An unpaid online order has no
bill; the customer is told it will come once payment completes.

Timing is a setting (`bill_timing`: `on_payment` default; `on_delivery` for
kitchens that prefer billing at handover). Whatever the setting, **one order
has at most one live bill**; asking again always resends the same document.

### 8.7 Who receives it

- **Customer:** WhatsApp document (§7.9) to the order's phone; email as well if
  an address is on file.
- **Owner:** copy on WhatsApp (`owner_copy_of_bill`), and always in the
  backend's Bills list.
- **Storefront:** order page offers **Download bill** after OTP or through the
  signed link sent on WhatsApp.

### 8.8 Asking for a bill in the chat

```
Customer: bill
Bot:      Which order is the bill for?            [list: last 10 orders]
            ANNAM-…4812 · 7 Sep · ₹260
            ANNAM-…3307 · 2 Sep · ₹180
            …
            My order isn't listed
```

- **A listed order that has a bill** → the PDF is sent again at once.
- **A listed order that is eligible but unbilled** (e.g. a catalog order the
  owner marked paid before billing existed) → billed now, sent.
- **A listed order not yet eligible** → "Your bill will be sent automatically
  once payment is completed" (or "…once your order is delivered" for COD).
- **Need a GST bill?** Before issuing, if the customer has no GST details on
  file, one button asks **GST bill · Normal bill**. GST bill collects GSTIN
  (15 characters, format and checksum validated), business name and billing
  address — saved on the customer for next time.
- **An order still in progress** (at the summary or awaiting payment): the
  bill keywords — *GST*, *GST bill* — collect GST details for *that* order
  instead of listing past ones, so its first bill is already a GST bill.
- **"My order isn't listed"** → the bot asks, one question at a time: date of
  the order, amount paid, what was ordered (free text), and GST details if
  wanted. It creates an **Invoice Request**, tells the customer "We'll send your
  bill within 24 hours" (period is a setting), and alerts the owner.
- If the customer says the order was placed on **Swiggy or Zomato** (button in
  the "not listed" step), the bot explains that the platform issues that bill
  and where to find it in their app — the kitchen must not bill it twice.

**The owner completes a request** from the backend's *Bill requests* queue: the
request opens a Quick bill form pre-filled with the customer's phone, GST
details and the text they sent; the owner picks the dishes and payment mode and
presses **Issue**. That creates a `manual` order, issues the bill, sends it to
the customer on WhatsApp, and closes the request. A request can also be
declined with a reason, which is sent to the customer.

Requests are rate-limited per phone number (default 5 a day) so the queue
can't be flooded.

### 8.9 GST details after a bill already exists

A bill, once issued, is never edited. If a customer asks for a GST bill after a
normal bill has been issued for that order, the system issues a **credit
note** against the first bill and a **new Tax Invoice** with the GST details,
in the same financial year, and sends both. The owner sees the pair linked in
the backend. Checkout (web) and the WhatsApp summary both offer "Need a GST
bill?" up front to make this rare.

### 8.10 Calculation

- `prices_include_tax` (setting, default **on** — customers expect the menu
  price to be what they pay): taxable value = price ÷ (1 + rate); tax = price −
  taxable value. Off: tax is added on top.
- Tax is computed **per line**, rounded half-up to the paisa; CGST and SGST are
  each half of the line tax, with any odd paisa assigned to CGST so the two
  always sum to the line tax exactly.
- Grand total rounded to the rupee with a visible **Round off** line (setting;
  default on). All stored amounts keep paise.
- **Intra-state vs inter-state:** place of supply is the delivery state. Same as
  the kitchen's state → CGST + SGST; different (courier items to another
  state) → IGST.
- **Delivery fee** is billed as a line at the same rate as the food by default
  (the delivery is part of the food service). This is an accountant decision
  and a setting (§21).
- Discounts reduce taxable value before tax.

### 8.11 Corrections and cancellations

- Issued bills are immutable. The model has no update path for issued
  documents; a test asserts it.
- Cancelling a billed order issues a **credit note** for the full amount
  (partial credit notes for partial refunds), linked to the original, sent to
  the customer.
- Bills are never deleted, including when a tenant is suspended or cancelled
  (§12.4). A cancelled tenant's export includes every bill.

### 8.12 The PDF

- WeasyPrint renders a Django template; the kitchen's logo and colours come from
  its theme. Two layouts: **A4** (default) and **80 mm thermal** for kitchens
  that print on a receipt printer.
- Stored in private object storage under an unguessable key; never served from
  a public URL. WhatsApp delivery uploads to Meta's media endpoint; storefront
  downloads use signed URLs valid for 15 minutes.
- Rendered on the worker, never in a web request.
- The PDF is rendered once at issue and stored; regenerating from data must
  produce the same totals (test).

### 8.13 For the accountant

Backend → **Bills → Export**, by month:

- CSV per document: number, date, type, buyer name, buyer GSTIN, place of
  supply, taxable value, CGST, SGST, IGST, round-off, total, payment mode,
  order number, channel — laid out to paste into GSTR-1.
- SAC summary for the month.
- A ZIP of every PDF.

### 8.14 Billing acceptance tests

- numbers are consecutive with no gaps, per tenant, per financial year; two
  concurrent payments never receive the same number (Postgres, threads)
- the format setting rejects anything that could exceed 16 characters
- 1 April starts sequence 1 of the new year
- a rolled-back transaction does not consume a number
- regular mode intra-state splits CGST/SGST exactly; inter-state uses IGST
- inclusive and exclusive pricing both produce totals that match the order
- composition mode prints "Bill of Supply" and the declaration, and no tax
- FSSAI number appears on every document type; a kitchen without one cannot
  issue (setup check)
- asking twice resends the same bill, never a second number
- a redelivered payment webhook produces one bill
- cancelling a billed order produces a linked credit note; the bill is
  unchanged
- GST details after issue produce credit note + new tax invoice
- "not listed" creates a request, alerts the owner, and fulfilment sends the bill
- a Swiggy/Zomato answer produces no request and no bill
- bills never leak between kitchens

---

## 9. Payments

### 9.1 Provider adapter

```python
class PaymentProvider(Protocol):
    def create_checkout(self, order) -> CheckoutSession      # web
    def create_link(self, order, expires_at) -> PaymentLink  # WhatsApp
    def verify_webhook(self, body: bytes, signature: str) -> bool
    def fetch(self, provider_ref: str) -> PaymentState       # lookup, the source of truth
    def refund(self, payment, amount) -> RefundState
```

Implementations: `razorpay` (per-tenant keys from `TenantSecrets`) and `manual`
(owner-recorded). Native WhatsApp Pay uses the same Razorpay account through
Meta's configuration; its `payment` webhook is verified with `fetch`.

### 9.2 Website checkout

Cart → phone (OTP by WhatsApp authentication template, §7.13) → address and
"Need a GST bill?" → summary → `create_order` → Razorpay Checkout → return page
polls order state → confirmation page. The bill and updates follow on
WhatsApp, which is the interlink Hari asked for (R2).

### 9.3 Webhook handling — `POST /pay/<slug>/razorpay`

1. Resolve tenant; verify `X-Razorpay-Signature` over the raw body with that
   tenant's webhook secret. Mismatch → 400, nothing stored.
2. Idempotency: the event id is unique on `PaymentEvent`; a repeat returns 200
   and does nothing.
3. **Confirm with `fetch`** before changing state — a webhook is a prompt to
   look, not proof.
4. In one transaction: record `Payment`, set `order.payment_status = paid`,
   append `OrderEvent`, issue the bill (number allocated here).
5. Queue: confirmation + bill to customer, alert to owner, extension events.
6. Return 200.

A reconciliation job every 15 minutes fetches the state of recent unpaid links,
so a lost webhook delays a confirmation by minutes instead of losing it.

### 9.4 Manual payments

Owner records "Paid by UPI to owner" (optional UTR) or "Cash" from the order
page, the Today screen, or `PAID 4812` on WhatsApp (§7.10). This is what makes
billing work for Annam **before** Razorpay is connected: catalog orders are
paid the way they are paid today, and the owner marks them.

### 9.5 Cash on delivery

`cod` flag; optional maximum order value and zone restrictions. Order confirmed
as `cod_pending`; bill issued on delivery or when cash is recorded.

### 9.6 Refunds

Full or partial, from the order page. Razorpay refunds go through the API;
manual payments are recorded. Each refund issues a credit note (§8.11) and a
WhatsApp message.

### 9.7 Payment acceptance tests

- a bad signature changes nothing; a good one pays exactly once
- a webhook for tenant A's order cannot change tenant B
- state is only changed after `fetch` agrees
- a link unpaid for 60 minutes cancels the order and sends Order again
- reconciliation pays an order whose webhook never arrived
- native WhatsApp Pay amounts are value × 100 with offset 100 and match the
  order total to the paisa
- manual PAID by a non-owner number is refused

---

## 10. Storefront

### 10.1 Direction

**Look and merchandising from sweetkaramcoffee.in; kitchen model from Annam;
photography from Annam.** Sweet Karam is the layout reference, not a brand to
imitate.

| Borrow from the reference | Don't borrow |
|---|---|
| Neutral ground that lets food photography carry the page | Pack-size dropdowns — a meal is one portion |
| Product grid: square photo, name, price, add — 2 across on a phone, 4 on desktop (built) | Strike-through "was ₹X" pricing on daily meals |
| Full-width campaign slider, smaller promo tiles beneath | Star ratings or review counts — there is no review system, and inventing them is dishonest |
| Shop-by-category tiles | "Limited drop" urgency — the honest urgency is the slot cutoff |
| Sticky header with cart count | Gift hampers, international shipping |

What the kitchen model requires and a packaged-goods store doesn't: today /
tomorrow and slot tabs, closed slots shown as closed, the cutoff time visible,
pincode before checkout, minimum-order state, the kitchen's phone prominent.

### 10.2 Pages

| Route | Page |
|---|---|
| `/` | Home: hero slider, promo tiles, today's dishes grid, shop by category, meal times, owner-chosen sections |
| `/menu/` | Today/tomorrow, slot tabs, product grid (built) |
| `/c/<slug>/` | Category — e.g. Snacks, Sweets |
| `/collections/<slug>/` | Curated collection — e.g. Krishna Jeyanthi specials, with start/end dates |
| `/item/<id>/` | Dish detail: photos, description, veg mark, price, availability by slot |
| `/cart/` | Cart (built) |
| `/checkout/` | Phone + OTP, address, GST bill option, summary, pay |
| `/order/<order_no>/` | Confirmation, live status, **Download bill** |
| `/track/` | Order number + phone |
| `/p/<slug>/` | Owner pages: festival offer, delivery cashback, refund policy, about, contact (built) |

### 10.3 Hero and campaigns (from the OpenCode brief)

- **Image-only hero.** Campaign artwork usually carries its own text; the page
  never overlays a second heading or button on it. A visually hidden H1 keeps
  the page accessible.
- **Up to three hero slides**, each independently managed: internal name,
  alt text, **desktop artwork and mobile artwork**, link (internal page,
  category, collection, or none), start and end date/time, active flag, order.
- Separate **promo tile** placement (three smaller images below the hero) —
  never derived from hero records.
- Only published, in-window slides render; zero slides collapses the hero.
- Autoplay with a visible pause control, pause on focus/hover, no autoplay
  under `prefers-reduced-motion`; first image loaded eagerly with explicit
  dimensions.

### 10.4 Menu behaviour (built, kept)

Daily and weekly planning from one table (`MenuSchedule`); dated rows override
the weekly template; cutoffs enforced in `slot_is_open`; the menu lands on the
next slot that can still be ordered; the cart re-prices from the live menu on
every read and never lets a lunch dish into a dinner order.

### 10.5 Fixes carried in

Prices show paise when they have them (₹120.50, not ₹121). Tenant timezone is
activated per request. Logo and showcase images move from Annam's old CDN into
our own storage before the old site is switched off.

### 10.6 Storefront acceptance

- a customer can go from home to paid order on a phone, and receive the bill on
  WhatsApp
- an out-of-window hero slide never renders; a desktop-only slide shows its
  desktop art on mobile rather than nothing
- a collection outside its dates 404s with a friendly page
- a suspended kitchen shows its menu with "not accepting orders" and no
  checkout
- the bill download works only through OTP or a valid signed link

---

## 11. Owner backend

`/manage/` on the kitchen's own domain. Not Django admin — that is SEER's
super admin. Built for a phone first, because owners run kitchens from their
phones.

### 11.1 Access

- Login by phone with WhatsApp OTP (password optional).
- Roles: **owner** (everything), **manager** (everything but settings, staff
  and credentials), **staff** (Today and Orders only).
- `restricted` kitchens (§12.4): every write except billing and payments of
  the subscription is blocked by one decorator, with a banner explaining why.
  Reading orders and issuing bills to customers **stay allowed** — a customer's
  bill must never be held hostage by the kitchen's subscription.
- Every write records who made it.

### 11.2 Today — the landing screen

Orders for today by slot with status, one-tap advance, unpaid and COD counts,
revenue, bill requests waiting, sold-out toggles. New orders appear within 15
seconds (HTMX polling) with a sound.

### 11.3 Orders

Filter by date, slot, channel, status, payment; detail shows the event trail,
payment, bill and messages sent. Actions: advance, cancel (with reason), mark
paid (UPI/cash + reference), record cash collected, refund, resend bill,
download bill.

### 11.4 Bills

- List of every bill and credit note, searchable by number, phone, order.
- **Quick bill**: phone (existing customer autocompletes), dishes from the menu
  or free lines, delivery fee, payment mode, GST details → issues a `manual`
  order and its bill, sends it on WhatsApp. Target: under a minute.
- **Bill requests** queue (§8.8): open, fulfil (opens Quick bill pre-filled),
  decline with reason.
- **Export** for the accountant (§8.13).
- **Billing settings**: legal name, address, state, GSTIN, FSSAI, GST mode,
  rate, SAC, prices-include-tax, number format with a live preview and the
  16-character check, footer, logo, A4/thermal.

### 11.5 Menu

Two editors from the same data, chosen by `menu_mode`: **day view** (date,
column per slot, availability, quantity limit, price override) and **week
view** (the standing template). Both have **Copy yesterday / Copy last week**,
**Mark sold out**, and a visible marker where a day overrides the week with
one-click revert. Dish management: name, description, price, photos, veg,
category, fulfilment (delivery slot / courier), WhatsApp catalog SKU. CSV
import and export.

### 11.6 Delivery

Zones (pincode, area, fee, minimum, slots served). Courier shipping rules for
courier items (flat fee, free above an amount, states served).

### 11.7 Storefront content

Hero slides and promo tiles (upload desktop/mobile art, schedule, preview,
publish), categories and collections, home sections order, navigation menu,
pages (markdown with preview: festival offers, delivery cashback, refund
policy…), theme colours and logo.

### 11.8 WhatsApp assistant

Copy editor (every message by copy key, with the default shown beside the
override and a preview in a phone frame), keyword lists, main-menu options,
kitchen-closed window and wording, follow-up toggles, optional update toggles,
owner numbers, template status list.

### 11.9 Connections — "like SeerDesk"

| Field | Behaviour |
|---|---|
| WhatsApp phone number ID, WABA ID | stored and shown |
| WhatsApp access token, app secret | **write-only** — shown as `••••••••4f2a`, replaceable, never read back (built) |
| Webhook URL and verify token | shown with copy buttons |
| **Test connection** | server-side Graph call; plain-language result |
| Razorpay key ID | stored and shown |
| Razorpay key secret, webhook secret | write-only |
| Razorpay webhook URL | shown with copy button |
| **Test connection** | server-side Razorpay call |
| Live / test mode | test mode lets the owner place a ₹1 order end to end |

Unlike SeerDesk's reveal toggle, secrets never return to the browser — a
compromised owner login must not walk away with keys that move money.

### 11.10 Customers, inbox, reports

- **Customers:** phone, name, orders, lifetime value, last order, GST details,
  opt-in state, notes.
- **Inbox:** §7.11.
- **Reports:** sales by day, slot, dish, channel; payments by mode; bills
  issued; **WhatsApp messages sent this month and estimated cost** (from
  `OutboundMessage` × the utility rate the owner enters).

### 11.11 Settings and staff

Brand, tagline, timezone, kitchen hours, slots and cutoffs, COD and payment
options, staff logins and roles, subscription status with a pay link.

---

## 12. Platform — super admin, onboarding, subscriptions

### 12.1 Super admin

Django admin on the platform host (no tenant context — platform code opts into
`all_tenants()` explicitly). Provisioning form (§6.7), feature flags, presets,
theme overrides list, extension settings, and a **health view** per kitchen:
orders in the last 7 days, last order, WhatsApp and Razorpay test status,
template approvals, failed messages, subscription state.

### 12.2 Impersonation

View a kitchen's backend as its owner for support. Every request is written to
`AdminAuditLog`. Impersonation cannot place orders, issue bills, or change
credentials.

### 12.3 Subscriptions

₹5,000/month per kitchen, collected by **Razorpay Subscriptions with a UPI
autopay mandate** set up at onboarding, so non-payment is the exception rather
than a monthly chase. Setup fee billed once by SEER. SEER's own invoices to
clients come from SEER's books, not from the kitchen's bill series.

### 12.4 The suspension ladder

| Rung | When | Kitchen owner | Customers |
|---|---|---|---|
| `active` | paid | everything | everything |
| `past_due` | day 1–6 | banner with pay link, WhatsApp reminders | nothing changes |
| `restricted` | day 7–13 | backend read-only except orders, bills and paying | nothing changes |
| `suspended` | day 14+ | full read access, exports, can pay to restore | menu visible, ordering off, bot gives the kitchen's phone number; **bills already owed are still sent** |
| `cancelled` | manual only | export handed over | site off |

Transitions run at 04:00 kitchen time, one rung at a time, never skipping;
**Grant grace** freezes the ladder until a date; paying returns to `active`
from any rung. No rung deletes data.

---

## 13. Data model

`T` = subclasses `TenantOwnedModel` (scoped, fails closed). `E` = exempt, with
the reason on the model. **Bold** = new or changed.

### 13.1 Tenancy and platform

| Model | | Fields (abridged) |
|---|---|---|
| Tenant | — | slug, name, primary_domain, status |
| TenantDomain | E | hostname, is_primary |
| TenantConfig | E | brand, tagline, theme, support_phone, timezone, menu_mode, hours, features, **owner_phones[]**, **kitchen_closed_window**, **bot_idle_reset_hours** |
| TenantSecrets | E | WhatsApp ids and encrypted token/app secret, **inbound_adapter** (`direct`/`relay`), **legacy_forward_url**, n8n send URL, Razorpay keys, live mode |
| TenantUser | T | user, role |
| **BillingProfile** | E | legal_name, address, state, state_code, gstin, fssai_no, gst_mode, tax_rate, sac, prices_include_tax, number_format, round_total, delivery_fee_taxable, footer, layout |
| **Preset** | — (file) | slots, copy, flags, template pack, theme, pages |
| **ExtensionConfig** | T | key, enabled, settings |
| **Subscription**, **SubscriptionInvoice** | — (platform) | amount, period, status, grace_until, mandate_id |
| **AdminAuditLog** | — | actor, tenant, action, detail, at |

### 13.2 Catalog and delivery

| Model | | Fields |
|---|---|---|
| Slot | T | key, label, order_cutoff, delivery window, sort, active |
| MenuCategory | T | name, **slug, image, description, show_on_home**, sort |
| MenuItem | T | name, description, price, image, is_veg, tags, active, **retailer_id** (unique per tenant), **fulfilment** (`scheduled`/`courier`), **tax_rate** (override), **sac** (override) |
| **MenuItemImage** | T | item, image, alt, sort (gallery) |
| MenuSchedule | T | item, slot, mode (date/weekday), on_date/weekday, available, qty_limit, qty_sold, price_override |
| **Collection** | T | slug, title, description, image, items, starts_at, ends_at, **keywords[]** (WhatsApp triggers) |
| DeliveryZone | T | pincode, area, fee, min_order, slot_keys |
| **ShippingRule** | T | name, flat_fee, free_above, states[] (courier) |
| **CatalogSyncLog** | T | item, action, result, at |

### 13.3 Content

| Model | | Fields |
|---|---|---|
| Page | T | slug, title, body (markdown), published, nav, sort |
| **Campaign** (replaces Banner) | T | placement (`hero`/`promo`/`announcement`), name, alt, desktop_image, mobile_image, link_type, link_target, starts_at, ends_at, active, sort |

### 13.4 Customers and orders

| Model | | Fields |
|---|---|---|
| Customer | T | phone, name, email, source, **language**, **gstin, business_name, billing_address**, **marketing_opt_in, opt_in_at**, notes |
| Address | T | line1, line2, landmark, pincode, zone, **lat, lng**, is_default |
| Order | T | order_no, customer, channel, **source**, status, payment_status, **payment_mode**, **fulfilment**, slot (**nullable** for courier), delivery_date (**nullable** for courier), items (snapshot), address (snapshot), subtotal, delivery_fee, discount, total, **buyer_gst** (snapshot), **external_ref** (catalog wamid), **rider_name, rider_phone**, placed_at, cancelled_reason |
| OrderEvent | T | order, from, to, actor, note, at |
| **OtpChallenge** | T | phone, code_hash, expires_at, attempts |

### 13.5 Billing and payments

| Model | | Fields |
|---|---|---|
| **InvoiceSequence** | T | series (`bill`/`credit`), fy, next_no — locked with `select_for_update` |
| **Invoice** | T | kind (`tax_invoice`/`bill_of_supply`/`bill`/`credit_note`), number, fy, order, original (for credit notes), seller (snapshot), buyer (snapshot), lines (snapshot with tax), taxable, cgst, sgst, igst, round_off, total, amount_words, payment_mode, payment_ref, pdf, issued_at, sent_customer_at, sent_owner_at |
| **InvoiceRequest** | T | customer, phone, order (nullable), details, wants_gst, gst details, status (`open`/`fulfilled`/`declined`), invoice, reason, handled_by |
| **Payment** | T | order, provider, provider_ref, method, amount, status, raw |
| **PaymentEvent** | T | provider, event_id (unique per tenant), payload, processed_at |
| **Refund** | T | payment, amount, provider_ref, credit_note |

### 13.6 WhatsApp

| Model | | Fields |
|---|---|---|
| OutboundMessage | T | to, payload, purpose, status, provider, provider_message_id, attempts, last_error, dedupe_key, **delivered_at, read_at, template_fallback** |
| **WaSession** | T | phone (unique per tenant), state, data, updated_at, **bot_paused_until**, **language** |
| **WaInboundMessage** | T | phone, kind, body, raw, wamid (unique per tenant), at, handled, forwarded |
| **WaTemplate** | T | name, category, language, status, rejection_reason, body, variables |
| **BotCopy** | T | key, language, text |
| **KeywordSet** | T | intent, words[] |

---

## 14. Service layer and integration contracts

Views, the WhatsApp worker and scheduled jobs call these; none of them contain
business rules of their own.

| Module | Function | Notes |
|---|---|---|
| `catalog.services` | `resolve_menu(date, slot)`, `open_slots(date)`, `slot_is_open(slot, date, now)` | built |
| `delivery.services` | `zones_for_pincode(pin, slot_key)`, `normalise_pincode(raw)`, `shipping_for(address, items)` | shipping new |
| `orders.services` | `create_order(...)`, `advance_status(order, to, actor)`, `get_or_create_customer(...)` | built; extend for courier, source, payment_mode |
| `billing.services` | `issue_bill(order, *, gst_details=None) -> Invoice`, `issue_credit_note(invoice, amount, reason)`, `allocate_number(tenant, series)`, `render_pdf(invoice)`, `request_bill(customer, details)`, `fulfil_request(request, order)` | new |
| `payments.services` | `request_payment(order, channel)`, `handle_provider_event(tenant, body, sig)`, `mark_paid_manually(order, mode, ref, actor)`, `refund(...)`, `reconcile_recent()` | new |
| `whatsapp.inbound` | `parse(payload) -> list[InboundEvent]`, `record(event)` | new |
| `whatsapp.conversation` | `handle(session, event, ctx) -> Result(state, replies, actions)` | new, pure |
| `whatsapp.actions` | executor for `CreateOrder`, `RequestPayment`, `IssueBill`, `CreateBillRequest`, `NotifyOwner`, `PauseBot`, `SavePincode`, `SaveAddress` | new |
| `whatsapp.owner` | `handle_owner_command(tenant, phone, text)` | new |
| `whatsapp.catalog` | `sync_catalog(tenant)`, `map_catalog_order(event)` | new |
| `messaging.services` | `queue(...)`, `send_now(...)`, `deliver(...)`, `dispatch_pending()`, **`send_or_template(...)`** | built; template fallback new |
| `notifications` | `on_order_event(order, event)` → the §7.8 table | new |
| `extensions` | `emit(tenant, event_name, payload)` | new |

**Scheduled jobs** (tenant-aware; each runs inside `tenant_context` per
kitchen, in the kitchen's timezone):

| Job | When |
|---|---|
| `send_pending_messages` | every minute |
| `payment_reminders_and_expiry` | every 5 minutes |
| `reconcile_payments` | every 15 minutes |
| `menu_roll_and_catalog_sync` | 04:00 kitchen time |
| `owner_morning_summary` | 04:00 kitchen time (configurable) |
| `billing_ladder` (subscriptions) | 04:00 kitchen time |
| `template_status_refresh` | hourly |
| `session_expiry` | hourly |
| `prune_old_messages` | daily (keep 180 days, configurable) |

---

## 15. Security, privacy and compliance

| Area | Rule |
|---|---|
| Tenant isolation | `TenantOwnedModel` fails closed; the tripwire test fails the build on any unscoped tenant model; no tenant slug may appear in `apps/` |
| Meta webhooks | `X-Hub-Signature-256` HMAC-SHA256 over the raw body with the tenant's app secret; reject before storing anything |
| Razorpay webhooks | `X-Razorpay-Signature` over the raw body with the tenant's webhook secret; state changes only after a `fetch` agrees |
| Credentials | Fernet-encrypted at rest (built); write-only in every form; never logged; never in documents or the repo. **The WhatsApp token that sat in plain text in `ANNAM_N8N_WORKFLOWS_CLAUDECODE.md` must be rotated.** |
| Bills | private storage, unguessable keys; WhatsApp delivery via media upload; web download via 15-minute signed URL or OTP |
| OTP | 6 digits, stored hashed, 5-minute expiry, 5 attempts, rate-limited per phone and per IP |
| Owner WhatsApp commands | only from numbers in `owner_phones`; `CANCEL` and `PAID` echo the order and require `YES` to confirm |
| Redirects | only same-site paths (built guard) |
| Audit | owner writes and every super-admin action recorded with actor and time |
| Personal data | phone, name and address used only to fulfil orders and send bills; marketing messages only with a recorded opt-in; the owner can export or erase a customer's data on request (bills are retained as legal records, with the erasure noted) |
| Bills as records | never edited, never deleted — corrections by credit note |

---

## 16. Hosting and operations

- **Host:** Hetzner CX33, Falkenstein (≈₹880/month). The Hetzner account's
  manual verification was still pending at the time of writing; **until it
  clears, deploy to the existing EC2 t3.medium**, which has headroom, and move
  later with the n8n cutover runbook.
- **Compose services** with memory caps: `web` (gunicorn, 3 workers), `worker`
  (2), `scheduler`, `postgres` (1 GB, `shared_buffers` 512 MB,
  `max_connections` 40), `redis` (128 MB), `caddy`, and `n8n` for the older
  clients. 2 GB swap as a backstop.
- **TLS:** Caddy on-demand TLS with an `ask` endpoint that approves only
  hostnames present in `TenantDomain`. Cloudflare free tier in front.
- **Storage:** object storage with two buckets — public (menu photos, hero art)
  and private (bills).
- **Backups:** nightly `pg_dump` to versioned object storage; the bills bucket
  versioned; **a restore rehearsed before the first client goes live and
  monthly after.** At three paying kitchens, move PostgreSQL to a managed
  service with point-in-time recovery.
- **Monitoring:** `/healthz`; external uptime check; errors emailed to SEER; a
  super-admin panel of failed and abandoned messages and failed payments across
  kitchens.
- **Deploys:** one command; migrations run before the new code takes traffic;
  no editing files on the server.

---

## 17. Build phases

Ordered so **Annam gets working bills first**, while the old website and the
old n8n bot keep running. Every phase ends in something a customer or the
owner can use. Estimates assume evenings and weekends.

### Phase A — Foundation (≈1 week)

- PostgreSQL in dev and prod; settings from environment; `.env.example`.
- Worker and scheduler (django-q2 or Huey + Redis); scheduled jobs run per
  tenant in the tenant's timezone.
- Activate the tenant's timezone per request (D1); show paise (D2).
- Feature-flag registry; `BillingProfile`; `MenuItem.retailer_id` and
  `fulfilment`; `Order.source`, `payment_mode`, nullable slot/date for courier.
- Preset loader with `daily-meals` and `snacks-courier`.
- Guard tests: no tenant slug in `apps/`; every flag both states.

**Done when:** the suite runs on PostgreSQL; a concurrency test proves
`select_for_update` holds; a preset provisions a kitchen into an empty
database.

**Local completion, 28 September 2026:** All 189 tests pass on PostgreSQL 17;
PostgreSQL and Redis 7 are running
through Compose. The Django suite ran on PostgreSQL with a two-thread
`select_for_update` test, the no-slug guard, both states for every registered
flag, and clean provisioning for both presets. The Huey consumer started with
two workers and its minute scheduler; message dispatch executes per tenant,
and the 04:00 local-day handoff records one durable row per kitchen/day. The
current Annam SQLite records were copied into PostgreSQL without changing the
original file. Exact copy/template-pack values from presets are stored in
`TenantConfig.preset_data` until the Phase C copy/template models exist. The
new courier fields are schema groundwork; courier checkout is not enabled.

### Phase B — Bills (≈2 weeks) · first release to Annam

- Billing engine: `InvoiceSequence`, `Invoice`, credit notes, three tax modes,
  §8.10 calculation, Rule 46 numbering, PDF (A4 + thermal), private storage.
- Owner backend v0: login by WhatsApp OTP, Today, Orders, Quick bill, mark paid,
  Bill requests queue, Bills list and export, Billing settings with preview.
- WhatsApp inbound front door: signature, dedupe, statuses, **legacy forward to
  n8n** for everything not yet handled.
- Handled natively: catalog `order` messages → orders (§7.5 B); **bill on
  request** (§8.8); owner alerts; owner commands `PAID`, `BILL`, `ORDERS`.
- Document sending via media upload; `send_or_template`; `bill_ready` and
  `order_confirmed` templates submitted.
- Deploy to production (EC2 interim or Hetzner).

**Done when**, on Annam's real number:
1. a customer sends a cart from the WhatsApp catalog and gets a summary;
2. the owner replies `PAID 4812` and the customer receives a correct PDF bill
   on WhatsApp within a minute, with a copy to the owner;
3. a customer types "bill", picks the order, and receives the same bill again;
4. a customer with an order from the old website asks for a bill, the owner
   fulfils it from the queue, and the bill arrives;
5. every other message still gets Annam's familiar n8n replies.

### Phase C — The WhatsApp assistant (≈2 weeks)

- Conversation engine (pure) and action executor.
- Every parity row in §7.3; guided ordering (§7.5 A); snacks courier branch;
  seasonal collections with keywords; kitchen-closed notice; contact fallback;
  support hand-off; My orders / track; order again.
- Inbox with take-over / resume.
- Copy keys and keyword sets with defaults; owner copy editor (basic).
- Switch features from forwarded to handled one at a time; when a week passes
  with nothing forwarded, clear `legacy_forward_url` and retire Annam's n8n
  flows.

**Done when:** a scripted table of every §7.3 row passes; Annam's bot runs
entirely in SeerKitchen; forwarded-event count is zero.

### Phase D — Payments and updates (≈1.5 weeks)

- Razorpay adapter; payment links with 20-minute reminder and 60-minute expiry;
  webhook + `fetch` + idempotency; reconciliation job.
- COD; refunds with credit notes.
- Every row of §7.8 with dedupe keys and template fallback; per-kitchen
  toggles.
- Native WhatsApp Pay (`order_details` / `order_status`) behind its flag.

**Done when:** an order placed in chat is paid by link, billed and confirmed
with no human step; a lost webhook is recovered by reconciliation; a cancelled
paid order produces a refund and a credit note on WhatsApp.

### Phase E — Storefront completion (≈2 weeks)

- Checkout with WhatsApp OTP and "Need a GST bill?"; order page with Download
  bill; track page.
- Hero campaigns (§10.3), promo tiles, category and collection pages, dish
  detail.
- Annam's photographs (originals from the client) and assets moved off the old
  CDN (D5).
- Catalog sync (§7.6) behind its flag.

**Done when:** a phone user goes from home to paid order and gets the bill and
updates on WhatsApp; Lighthouse mobile accessibility ≥ 95.

### Phase F — Owner backend complete (≈2 weeks)

- Menu editors (day/week, copy yesterday, sold out, override marker), CSV
  import, photos.
- Zones and courier rules; storefront content editor with preview and publish;
  copy editor with phone preview; keyword lists; notification toggles.
- Connections page (write-only secrets, test buttons, test mode).
- Customers, reports including WhatsApp message counts and estimated cost.
- Full owner WhatsApp command set (§7.10).

**Done when:** the Annam owner runs a full day — menu, orders, bills, a hero
change — without SEER.

### Phase G — Platform and the plug-and-play kit (≈1 week)

- Provisioning wizard with presets; automatic template submission and status.
- Subscriptions with UPI autopay; suspension ladder job; grace; health view;
  impersonation with audit.
- Extensions: `event_webhook`, `sheets_export`, `group_tracking`.
- Client onboarding guide (written once).

**Done when:** a second, fictional kitchen is provisioned from nothing to a test
order with a bill in under an hour, with no code change.

**Custom-domain workflow update, 21 October 2026:** Owner domain settings now
prepare claims, verify TXT ownership and DNS, check provider registration and
HTTPS, and allow explicit primary selection/removal. Production connections
default off; Annam’s live DNS is unchanged. Render registration and Caddy
on-demand TLS integration require deployment configuration and staging-domain
validation before cutover. See [custom-domains.md](custom-domains.md). Existing
n8n automation remains in use; the earlier native-bot retirement plan is not
a prerequisite for this domain feature.

### Phase H — Annam cutover and hardening (≈1 week)

- Storefront on a staging subdomain, reviewed with Annam.
- DNS cutover of `annamfood.in` at 04:00 on the quietest day; old URLs
  redirected; old provider kept two weeks, then cancelled.
- Backups rehearsed; monitoring live; token rotation confirmed.

**Done when:** Annam's website, WhatsApp, payments and bills all run on
SeerKitchen, and the old provider and the old n8n flows are off.

**Total: roughly 12–13 weeks.** Phase B alone solves Annam's main problem and
is worth releasing on its own.

### Every phase — definition of done

- `uv run python -m pytest -q` green, including the phase's listed behaviours
- `manage.py check` clean; migrations committed with the models
- isolation tripwire and no-slug test pass
- anything kitchen-specific is a setting, flag, copy key or preset
- this plan updated where reality differed

---

## 18. Testing rules

1. **Never derive a time from the wall clock in a test.** Pin it. A fixture that
   computed "now + 3 hours" broke nine tests every evening after 21:00 IST.
   Every time-sensitive test runs at least at 12:00 and 23:30.
2. Run tests as `uv run python -m pytest` — console scripts break when the
   project folder moves.
3. Test names are sentences describing behaviour.
4. The conversation engine is tested as tables of `(state, event) → (state,
   replies, actions)`, with no network and no database.
5. Webhooks are tested against recorded payload fixtures (Meta: text, button,
   list, order, location, statuses, payment; Razorpay: payment captured,
   link paid, refund).
6. Bills are tested on their numbers and totals, not on pixels.
7. Invoice numbering has a PostgreSQL concurrency test with threads.
8. Every flag is tested in both states; every preset provisions cleanly.
9. Every new tenant-owned model gets an isolation test (the tripwire enforces
   the base class; the test proves the data doesn't leak).

---

## 19. Moving Annam across

Annam keeps running the whole time. Nothing switches over in one night except
the website's DNS at the very end.

| Step | Phase | What happens | Customers notice |
|---|---|---|---|
| 1 | B | Meta webhook for Annam's number points at SeerKitchen (`direct`), with `legacy_forward_url` = the existing n8n inbound webhook | nothing |
| 2 | B | SeerKitchen handles catalog carts, bill requests and owner messages; forwards everything else to n8n | they can now get bills |
| 3 | C | Bot features move from forwarded to handled, one at a time | the same bot, now able to take orders |
| 4 | C | Forwarding reaches zero for a week → setting cleared → Annam's n8n flows switched off | nothing |
| 5 | D | Razorpay connected; payment links and updates live | pay in chat |
| 6 | E–F | Storefront built on a staging subdomain with Annam's photos, pages and hero art; owner trained | nothing yet |
| 7 | H | `annamfood.in` DNS moved at 04:00; old paths redirected | a new website |
| 8 | H | Old provider cancelled after two weeks | nothing |

Rollback at steps 1–4 is one setting: point the Meta webhook back at n8n.

---

## 20. Risks and traps

| Risk | Mitigation |
|---|---|
| Wrong tax mode or rate produces wrong bills | Billing can't go live until the Billing settings are complete, a sample bill is previewed, and the kitchen confirms it (their accountant's decision, §21) |
| Invoice number gaps or duplicates | PostgreSQL row lock; concurrency test; numbers allocated only inside the issuing transaction |
| WhatsApp costs from 1 Oct 2026 | one message per step; optional updates off by default; monthly count and estimate in reports |
| Templates rejected by Meta | plain utility wording; submitted at provisioning; go-live waits for approval |
| Meta catalog and menu drift | catalog orders always re-priced; unmapped items refused and flagged; optional sync |
| A webhook lost or repeated | idempotency keys everywhere; reconciliation job; `fetch` before trusting |
| Cross-tenant leak | fail-closed scoping; tripwire; isolation tests |
| One server | tested restores; managed database at three clients |
| Work stranded uncommitted | this happened for a month: git lock files on a mounted folder blocked every commit silently. Check `git status` and `git log` at the start of every session |
| Scope creep | each phase lists what it delivers; anything else waits for the next |
| Old-CDN images vanish at cutover | moved into our storage in Phase E |

---

## 21. Open decisions

| # | Decision | Default until decided | Who | Needed by |
|---|---|---|---|---|
| 1 | Annam's GST position: regular / composition / unregistered | `unregistered` (plain bill) | Annam's accountant | Phase B go-live |
| 2 | Tax rate and SAC | 5%, 996331 | accountant | Phase B |
| 3 | Menu prices include GST? | yes | Annam | Phase B |
| 4 | Delivery fee taxed at the food rate? | yes | accountant | Phase B |
| 5 | Bill number prefix | `AF` → `AF/26-27/00001` | Annam | Phase B |
| 6 | Bill timing | on payment; COD on delivery | Annam | Phase B |
| 7 | Owner numbers for alerts and commands | the admin number | Annam | Phase B |
| 8 | Keep ordering through the WhatsApp catalog | yes — familiar to customers | Hari / Annam | Phase B |
| 9 | Bill-request promise | "within 24 hours" | Annam | Phase B |
| 10 | Production host until Hetzner verifies | existing EC2 | Hari | end of Phase B |
| 11 | Cash on delivery | off | Annam | Phase D |
| 12 | Native WhatsApp Pay or links first | links first | Hari | Phase D |
| 13 | Snacks courier: fee rules and states served | flat fee, Tamil Nadu only | Annam | Phase C/E |
| 14 | Tamil copy | later (flag off) | Annam | Phase C/F |
| 15 | Source of Annam's photographs | originals from the client | Annam | Phase E |
| 16 | Old website URLs to preserve | category and product URLs | Hari | Phase H |
| 17 | AVR, DHC, TailorsKart move onto SeerKitchen | no | Hari | — |

---

## 22. Appendices

Illustrations for the sections above. Names, numbers and phone numbers are
invented. Wording is the default copy — every line a customer sees is a copy
key the kitchen can change (§6.1).

### 22.1 Sample conversations

**A. Guided order in the chat (§7.5 A) — a returning customer**

```
Customer: hi
Kitchen:  Vanakkam Priya! 🙏 What would you like today?
          [🍱 Food] [🍿 Snacks] [🎉 Seasonal]
Customer: [🍱 Food]
Kitchen:  Delivering to 600042 (Velachery). Pick a meal:      ← saved pincode, no question
          [list] Lunch · Mon 7 Sep · order by 10:30
                 Dinner · Mon 7 Sep · order by 16:00
                 Change pincode
Customer: [Lunch · Mon 7 Sep]
Kitchen:  Today's lunch 🍱                                     ← one list message, ≤ 10 rows
          [list] Veg Meals · ₹110 · 🟢
                 Sambar Rice · ₹90 · 🟢
                 Chicken Biryani · ₹180 · 🔴
                 …
Customer: [Veg Meals]
Kitchen:  Veg Meals · ₹110. How many?  [1] [2] [3]
Customer: [2]
Kitchen:  Your cart — Lunch, Mon 7 Sep
          Veg Meals × 2 ........ ₹220
          Delivery ............. ₹40
          Total ................ ₹260
          [Add more] [Checkout] [Clear]
Customer: [Checkout]
Kitchen:  Deliver to 12, 3rd Street, Velachery 600042?
          [Yes, this address] [New address]
Customer: [Yes, this address]
Kitchen:  Order summary
          Veg Meals × 2 · Lunch, Mon 7 Sep, 12:30–13:30
          Total ₹260 · Need a GST bill? Type GST before you confirm.
          [Confirm] [Change] [Cancel]
Customer: [Confirm]
Kitchen:  Order ANNAM-20260907-4812 is waiting for payment.
          [Pay ₹260]                                           ← cta_url to Razorpay link
          …customer pays…
Kitchen:  📎 Bill-AF-26-27-00012.pdf                           ← one document message
          "✅ Paid — order ANNAM-20260907-4812 is confirmed. Your bill is attached."
Kitchen:  Order another slot? [Dinner today] [Not now]
```

If the customer had not paid, at 20 minutes: *"Your order is waiting —
[Pay ₹260]"*; at 60 minutes: *"We've cancelled the unpaid order
ANNAM-20260907-4812. [Order again]"* (§7.7).

**B. Cart from the WhatsApp catalog (§7.5 B)**

```
Customer: 🛒 (sends a cart from the catalog: Veg Meals × 2 at ₹100)
Kitchen:  Got your cart! Lunch today (Mon 7 Sep) is the open slot.
          Veg Meals × 2 ........ ₹220   (price updated from ₹100)
          What's your delivery pincode?
Customer: 600 042
Kitchen:  We deliver to Velachery 🎉  Where should we deliver?
          Type the house and street, or share your location 📍
Customer: 12, 3rd Street
Kitchen:  Order summary … Total ₹260   [Confirm] [Change] [Cancel]
          …joins flow A at Summary…
```

Before payments go live (Phase B), the summary ends with *"The kitchen will
confirm and send payment details"*; the owner gets an alert, collects payment
as today, and replies `PAID 4812` — the bill goes out automatically.

**C. Asking for a bill — a listed order**

```
Customer: bill
Kitchen:  Which order is the bill for?
          [list] ANNAM-…4812 · 7 Sep · ₹260
                 ANNAM-…3307 · 2 Sep · ₹180
                 My order isn't listed
Customer: [ANNAM-…4812]
Kitchen:  📎 Bill-AF-26-27-00012.pdf  "Bill for order ANNAM-20260907-4812 · ₹260"
```

With no GST details on file and no bill yet: *"Do you need a GST bill?
[GST bill] [Normal bill]"* comes first (§8.8).

**D. Asking for a bill — an order the system doesn't know**

```
Customer: [My order isn't listed]
Kitchen:  Where did you order?  [Our website] [Phone / chat] [Swiggy / Zomato]
Customer: [Our website]
Kitchen:  Which date was the order? (e.g. 1 Sep)
Customer: 1 sep
Kitchen:  How much did you pay?
Customer: 450
Kitchen:  What did you order? A short note is fine.
Customer: 3 veg meals office lunch
Kitchen:  Do you need a GST bill?  [GST bill] [Normal bill]
Customer: [GST bill]
Kitchen:  Please send your GSTIN (15 characters).
Customer: 33AAACA0000A1Z5
Kitchen:  Business name for the bill?
Customer: Example Tech Pvt Ltd
Kitchen:  Billing address?
Customer: 4th floor, 22 OMR, Chennai 600096
Kitchen:  Thank you! We'll send your bill here within 24 hours.
          Request no. BR-0031.
Owner ← : 🧾 Bill request BR-0031 · Priya · +91 98xxxxxx10
          1 Sep · ₹450 · "3 veg meals office lunch" · website
          GST: 33AAACA0000A1Z5 Example Tech Pvt Ltd
          Complete it: https://annamfood.in/manage/bills/requests/31
```

The owner opens the link, picks 3 × Veg Meals, sets payment "UPI to owner",
presses **Issue**; the customer receives the Tax Invoice on WhatsApp and the
request closes. A wrong GSTIN is caught at the chat step (*"That GSTIN doesn't
look right — please check and send it again"*) rather than on the bill.

If the customer picks **Swiggy / Zomato**: *"Orders placed on Swiggy or Zomato
are billed by the app itself — open the order in the app and tap Invoice. We're
not allowed to bill those orders again."*

**E. The owner on WhatsApp (§7.10)**

```
Kitchen → Owner: 🟢 New paid order ANNAM-…4812
                 Lunch · Mon 7 Sep · Veg Meals × 2
                 12, 3rd Street, Velachery 600042 · ₹260 · Razorpay
Owner:  ORDERS
Kitchen: Mon 7 Sep
         Breakfast — 6 · all delivered
         Lunch (by 10:30) — 14 · 9 paid · 3 COD · 2 awaiting payment
         Dinner (by 16:00) — 3 · 3 paid
Owner:  PAID 4907 425112345678
Kitchen: Mark ANNAM-20260907-4907 (Rajesh · ₹180) paid, UTR 425112345678?
         Reply YES to confirm.
Owner:  YES
Kitchen: ✅ Paid. Bill AF/26-27/00013 sent to Rajesh and to you.
Owner:  OUT 4812
Kitchen: 🛵 4812 is out for delivery. Priya has been told.
Owner:  SOLDOUT biryani
Kitchen: "Chicken Biryani" is off today's Lunch and Dinner menus.
         The website and WhatsApp menu stop showing it now.
```

### 22.2 Payload sketches

Shapes for the builder. Field names follow Meta's Cloud API and India payments
documentation as checked on 28 September 2026 — confirm against the live docs
when implementing, and keep recorded fixtures of real payloads (§18, rule 5).

**Inbound catalog cart** — `messages[].type == "order"`:

```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "id": "<WABA_ID>",
    "changes": [{
      "field": "messages",
      "value": {
        "messaging_product": "whatsapp",
        "metadata": { "display_phone_number": "91…", "phone_number_id": "<PHONE_NUMBER_ID>" },
        "contacts": [{ "profile": { "name": "Priya" }, "wa_id": "9198xxxxxx10" }],
        "messages": [{
          "from": "9198xxxxxx10",
          "id": "wamid.HBgM…",
          "timestamp": "1788751920",
          "type": "order",
          "order": {
            "catalog_id": "<CATALOG_ID>",
            "text": "",
            "product_items": [
              { "product_retailer_id": "VEG-MEALS", "quantity": 2, "item_price": 100, "currency": "INR" }
            ]
          }
        }]
      }
    }]
  }]
}
```

Parse `quantity` and `item_price` whether they arrive as numbers or strings.
`item_price` is recorded on the inbound log for the "price updated" note and
**never used for the charge** (§7.5 B).

**Normalised event** (what the conversation engine receives):

```python
InboundEvent(
    tenant_id=7, wamid="wamid.HBgM…", phone="919800000010", name="Priya",
    kind="order", at=datetime(2026, 9, 7, 9, 2, tzinfo=IST),
    text=None, reply_id=None, location=None,
    cart=CatalogCart(catalog_id="…",
                     lines=[CartLine(retailer_id="VEG-MEALS", quantity=2,
                                     seen_price=Decimal("100"))],
                     note=""),
)
```

**Conversation engine test rows** (§18, rule 4):

| state | event | → state | replies | actions |
|---|---|---|---|---|
| `IDLE` | `order` cart, 1 open slot, pincode unknown | `ASK_PINCODE` | cart summary with "price updated" + pincode question | `StashCart` |
| `ORDERS` | `list` row `order:4812`, order billed | `IDLE` | — | `SendInvoice(order=4812)` |
| `ORDERS` | `list` row `not_listed` | `INVOICE_REQUEST.WHERE` | "Where did you order?" + 3 buttons | — |

**Outbound bill** — upload, then send:

```
POST /{PHONE_NUMBER_ID}/media   (multipart: file=<pdf>, type=application/pdf, messaging_product=whatsapp)
  → { "id": "<MEDIA_ID>" }
```

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "919800000010",
  "type": "document",
  "document": {
    "id": "<MEDIA_ID>",
    "filename": "Bill-AF-26-27-00012.pdf",
    "caption": "Bill for order ANNAM-20260907-4812 · ₹260"
  }
}
```

Outside the 24-hour window the same bill goes as the `bill_ready` utility
template with a document header (§7.13).

**Pay button** (payment link):

```json
{
  "type": "interactive",
  "interactive": {
    "type": "cta_url",
    "body": { "text": "Order ANNAM-20260907-4812 · ₹260\nLunch, Mon 7 Sep" },
    "action": { "name": "cta_url",
                "parameters": { "display_text": "Pay ₹260", "url": "https://rzp.io/i/…" } }
  }
}
```

**Native WhatsApp Pay** (`native_whatsapp_pay`) — `interactive.order_details`:

```json
{
  "type": "interactive",
  "interactive": {
    "type": "order_details",
    "body": { "text": "Lunch, Mon 7 Sep · 12:30–13:30" },
    "action": {
      "name": "review_and_pay",
      "parameters": {
        "reference_id": "ANNAM-20260907-4812",
        "type": "physical-goods",
        "payment_settings": [{
          "type": "payment_gateway",
          "payment_gateway": { "type": "razorpay", "configuration_name": "<name set in Meta Business Suite>" }
        }],
        "currency": "INR",
        "total_amount": { "value": 26000, "offset": 100 },
        "order": {
          "status": "pending",
          "items": [{ "retailer_id": "VEG-MEALS", "name": "Veg Meals",
                      "amount": { "value": 11000, "offset": 100 }, "quantity": 2 }],
          "subtotal": { "value": 22000, "offset": 100 },
          "tax":      { "value": 0, "offset": 100, "description": "GST included in prices" },
          "shipping": { "value": 4000, "offset": 100 }
        }
      }
    }
  }
}
```

`total_amount` = subtotal + tax + shipping − discount, in paise. The
`payment` webhook that follows is a hint: the app looks the payment up before
marking the order paid (§7.7).

**Extension event** (`event_webhook`, §6.5):

```
POST <configured URL>
X-SeerKitchen-Event: invoice.issued
X-SeerKitchen-Signature: sha256=<HMAC of body with the extension's secret>

{ "tenant": "annam", "event": "invoice.issued", "at": "2026-09-07T09:06:05+05:30",
  "invoice": { "number": "AF/26-27/00012", "total": "260.00", "order_no": "ANNAM-20260907-4812",
               "channel": "whatsapp", "customer_phone": "919800000010" } }
```

### 22.3 Bill layout (A4, `regular` mode)

Worked with the §8.10 rules: prices include 5% GST, tax per line, CGST/SGST
halves, rounded to the paisa.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [logo]  ANNAM FOODS                                          TAX INVOICE │
│ <legal name> · <address>, Chennai 6000xx                                 │
│ GSTIN <kitchen GSTIN>  ·  FSSAI Lic. No. <14 digits>                     │
├──────────────────────────────────────────────────────────────────────────┤
│ Invoice no.  AF/26-27/00012              Date   07-09-2026               │
│ Order        ANNAM-20260907-4812         Ordered on WhatsApp             │
│ Delivery     Lunch · Mon 7 Sep 2026      Place of supply  Tamil Nadu (33)│
├──────────────────────────────────────────────────────────────────────────┤
│ Billed to    Priya S · +91 98xxxxxx10                                    │
│ Deliver to   12, 3rd Street, Velachery, Chennai 600042                   │
├──────────────────────────────────────────────────────────────────────────┤
│ Item        SAC     Qty  Price*   Value    Taxable  CGST 2.5%  SGST 2.5% │
│ Veg Meals   996331   2   110.00   220.00   209.52     5.24      5.24     │
│ Delivery    996331   1    40.00    40.00    38.10     0.95      0.95     │
├──────────────────────────────────────────────────────────────────────────┤
│                                   Taxable value              247.62      │
│                                   CGST                         6.19      │
│                                   SGST                         6.19      │
│                                   Round off                    0.00      │
│                                   Total                     ₹260.00      │
│ Rupees Two Hundred Sixty only                                            │
│ Paid · Razorpay pay_… · 07-09-2026 09:06                                 │
│ * Prices include GST                                                     │
├──────────────────────────────────────────────────────────────────────────┤
│ <footer text set by the kitchen>                   For Annam Foods       │
│                                                    Authorised signatory  │
└──────────────────────────────────────────────────────────────────────────┘
```

For a registered buyer the "Billed to" block adds their GSTIN, business name
and billing address. The other modes change only the header and tax columns:

| Mode | Title | GSTIN line | Tax columns and totals | Extra line |
|---|---|---|---|---|
| `regular` | TAX INVOICE | kitchen GSTIN | as above (IGST column instead for inter-state courier) | — |
| `composition` | BILL OF SUPPLY | kitchen GSTIN | none — Value and Total only | "Composition taxable person, not eligible to collect tax on supplies" |
| `unregistered` | BILL | none | none — Value and Total only | — |

FSSAI number appears in every mode. The 80 mm thermal layout carries the same
fields stacked in one column.

A **credit note** uses the same layout titled CREDIT NOTE, numbered in its own
series (`AFC/26-27/00001`), and names the original bill number and date.

### 22.4 Glossary

| Term | Meaning here |
|---|---|
| WABA | WhatsApp Business Account — the client's own, holding their number, templates and catalog |
| 24-hour window | Period after a customer's last message in which free-form replies are allowed; outside it only approved templates |
| Template | A Meta-approved message shape (utility, marketing, authentication) used outside the window |
| `wamid` | Meta's id for a WhatsApp message; our dedupe key for inbound messages |
| Catalog / `retailer_id` | Meta's product list for the number; `retailer_id` is the SKU we share with it (`MenuItem.retailer_id`) |
| `cta_url` | Interactive message with one button that opens a URL — used for payment links and website hand-off |
| `order_details` / `order_status` | Meta's interactive messages for native WhatsApp Pay and its status updates |
| Tax Invoice / Bill of Supply / Bill | The three documents, by GST mode (§8.3) |
| Credit note | The document that reverses all or part of an issued bill; bills are never edited |
| GSTIN | 15-character GST registration number; validated by format and checksum |
| SAC | Services Accounting Code; 996331 for restaurant/food services by default |
| FSSAI number | Food licence/registration number; mandatory on every bill |
| FY | Indian financial year, April–March, e.g. `26-27`; bill numbers restart each FY |
| Place of supply | State where the food is delivered; decides CGST+SGST vs IGST |
| UTR | Bank reference for a UPI/IMPS payment, entered when the owner marks paid |
| Tenant | One kitchen on SeerKitchen |
| Flag / preset / copy key / extension | Customisation levels 2, 3, 1 and 5 (§6) |
| Legacy forward | Migration setting that passes unhandled WhatsApp events to the old n8n flow (§5.5, §19) |
| Relay | Inbound adapter for a client whose Meta webhook must keep pointing at n8n (§5.5) |

### 22.5 Other documents in `docs/`

| Document | Status |
|---|---|
| `PLAN.md` (this) | **Source of truth** |
| `../AGENTS.md` | Coding rules and invariants — always current |
| `adr/0001-messaging-architecture.md` | Decision record, still in force; §5.5 extends it to inbound |
| `n8n/wa-send-workflow.md` | The optional n8n sender (§5.5) |
| `CODEBASE_STATUS.md` | Snapshot of code state; §4 here is newer |
| `phase-3` … `phase-7` | Earlier phase breakdown; superseded by §17 |
| `OPENCODE_STOREFRONT_HANDOFF.md`, `storefront-redesign.md` | Storefront detail and fix list; direction in §10 wins |

### 22.6 Sources checked on 28 September 2026

- Meta — WhatsApp payments in India via payment gateway (`order_details`,
  `reference_id`, gateways, lookup before trusting the webhook):
  https://developers.facebook.com/documentation/business-messaging/whatsapp/payments/payments-in/pg/
- Meta — WhatsApp pricing:
  https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing
- Meta — catalogs overview:
  https://developers.facebook.com/documentation/business-messaging/whatsapp/catalogs/catalogs-overview/
- Courier — WhatsApp pricing changes, October 2026:
  https://www.courier.com/blog/whatsapp-pricing-changes-october-2026
- Catalog `order` webhook walkthrough:
  https://www.negocionoautomaticobr.com.br/blog/whatsapp/receber-pedido-catalogo-whatsapp-cloud-api-webhook-order-passo-a-passo
- Razorpay — payments on WhatsApp: https://razorpay.com/payments-on-whatsapp/
- CBIC — CGST Rules, Rule 46 (tax invoice contents, 16-character serial):
  https://taxinformation.cbic.gov.in/content/html/tax_repository/gst/rules/cgst_rules/active/chapter6/rule46_v1.00.html
- TaxGuru — FSSAI number on invoices from 1 October 2021:
  https://taxguru.in/corporate-law/fssai-food-businesses-mention-license-no-invoices-w-e-f-1st-october-2021.html
- Tax Garden — GST on restaurant and food services, 2026:
  https://taxgarden.in/blog/gst-on-restaurant-food-services-india-rates-rules-2026

Tax notes in this plan are research for the accountant conversation, not tax
advice; the kitchen's accountant confirms mode, rate, SAC and delivery-fee
treatment before billing goes live (§21).

### Website checkout implementation — 21 October 2026

The Django storefront now submits to the shared Django order book; the older
WordPress comparison above is not a second ordering system. Guest checkout
collects contact/address details, then shows a server-priced order review before
placing an unpaid `web` / `storefront` order. Razorpay and automatic message/bill
delivery remain separate work. Manual payment instructions are configurable;
staff must confirm receipt before a bill can be issued.

- Meal checkout requires an active delivery-zone pincode and explicit area choice
  when a pincode has several areas. Minimums, fees, today/tomorrow dates, active
  slots, cutoffs, unavailable dishes and configured closed dates are rechecked
  on submission. There is no pickup or out-of-zone bypass.
- Shop checkout uses **separate explicit approved Tamil Nadu pincodes**, a flat
  courier fee and a shop minimum under **Checkout & courier**. It is disabled by
  default. The kitchen must confirm actual courier coverage and enter its exact
  approved pincodes and charges; the platform does not guess state coverage from
  postal prefixes or claim unverified statewide delivery. Unlisted pincodes are
  blocked, even if they are in a meal delivery zone. Meals and shop goods remain
  separate carts/orders.
- Reviews are signed, browser/tenant bound, expire after 30 minutes, and include
  a fingerprint of details, quantities, live prices, delivery rules and tax
  settings. Changed prices or details require another review. A transaction and
  unique order reference make accepted-review retries return the original order.
- Receipts are private to the submitting browser session and tenant; guessing an
  order number cannot retrieve customer information. Guest checkout never loads
  an existing customer's address/history based on a supplied phone number.
- Item tax rates and order tax/rounding settings are snapshotted. Manual bill
  generation uses those frozen rates so subsequent tax-setting edits do not
  alter the accepted order total. Seller billing settings still need completion
  before bill issuance.

Before testing on Render, let the deployment apply the two migrations. In the
Annam admin, review **Delivery areas**, **Checkout & courier**, **Meal times** and
**Billing settings**. Do not enable courier ordering with unconfirmed coverage.

### Razorpay implementation update — 21 October 2026

The Django checkout now offers Razorpay alongside configured manual payment.
Mode-specific encrypted connections, signed checkout verification, independent
capture fetches, signed/deduplicated webhooks, retry-safe provider orders, private
customer bills, full owner-authorized refunds and refund/credit-note reconciliation
are implemented. Test payments never issue real fiscal bills. Payment mode and
account are frozen when the reviewed website order is placed.

The implementation uses tenant-owned `apps.payments` records rather than one
mutable test/live credential slot. Previously saved TenantSecrets credentials
are preserved as disabled mode-specific connections; owners explicitly verify
and enable them. See [razorpay.md](razorpay.md) for setup and recovery details.

Actual sandbox verification awaits Annam's keys and its Razorpay webhook setup.
Production collection needs activated live credentials and explicit live-mode
confirmation. n8n message synchronization and automatic WhatsApp bill delivery
remain separate; this change does not move the storefront's production domain.
