# SeerKitchen — the whole plan

One document, everything. The business, the architecture, what is built, and
what is left. Detailed implementation specs live in the per-phase files linked
from Part 6; this is the file to read first and the one to keep true.

**Conventions for anyone writing code live in `../AGENTS.md`.** Read that before
touching the codebase.

---

# Part 1 — What this is

A packaged ordering system for cloud kitchens, sold as a subscription. Each
kitchen gets a branded website on its own domain, a WhatsApp bot, and one order
and billing spine underneath both. Built once, configured per client.

## The problem it solves

Annam Foods runs two disconnected halves. A website bought from another
provider, where customers actually order and where the menu is updated by hand.
And a WhatsApp bot that shows a menu and collects a pincode but **cannot take
an order**. Website orders are invisible to WhatsApp. Nothing on WhatsApp
reaches the books. No shared customer, no shared bill, no shared anything.

Every small cloud kitchen has some version of this.

## What the product does

- **Storefront** on the client's domain — home, menu, offers, policy pages, real checkout
- **Owner backend** where he updates the menu daily or weekly, sees every order
  from both channels in one list, and manages zones, offers and content himself
- **WhatsApp bot** that takes a complete order, not just shows a menu
- **One order record** whichever channel it came from — same numbering, same
  invoice, same customer history, same reports

Every kitchen gets the same product. What differs is configuration, not code.

## Scope

Cloud kitchens only. Not restaurants with tables, not general e-commerce. The
narrowness is the point: slots, delivery zones, daily menus and kitchen hours
can be assumed rather than configured into existence.

---

# Part 2 — The business

| | |
|---|---|
| Setup fee | ₹5,000–8,000 one-time, excluding domain |
| Recurring | ₹5,000 / month per kitchen |
| Target scale | ~20 kitchens |
| Infra budget | ≤ ₹2,000 / month total, all clients |

## What the client pays for directly

Their own domain, their own WhatsApp Business account, their own Razorpay
account. These are legally and financially theirs, so the costs and the
compliance sit with them — and it keeps messaging and payment fees off your P&L
entirely.

## What you pay for

| Item | Monthly |
|---|---|
| Hetzner CX33 — 4 vCPU, 8 GB, everything on it | ≈ ₹880 |
| Cloudflare free tier — CDN, TLS, DDoS | ₹0 |
| Object storage — media, invoices, backups | ₹0–250 |
| Your own domain | ≈ ₹100 |
| **Total at 20 clients** | **≈ ₹1,000–1,250 · ₹50–60 per kitchen** |

Roughly half the ceiling, with room to move to a CX43 (8 vCPU, 16 GB, ≈₹1,650)
and stay inside it. At 20 clients that is ~1% of ₹1,00,000/month recurring.

## The migration that pays for itself

The current EC2 t3.medium costs ~₹3,000/month and serves two tenants. Moving
n8n for AVR, DHC and TailorsKart onto the same Hetzner box lets you **shut the
EC2 down entirely** — one ₹880 server running the new platform and every
existing client's automation. Largest single saving available.

Runbook for that cutover exists separately; the short version is that all n8n
state lives in `~/.n8n`, the cutover is about five minutes, and the six things
that break silently are the encryption key, version mismatch, two instances
live at once, DNS TTL, timezone, and `WEBHOOK_URL`.

## Hosting choices considered

| Option | Specs | Monthly | Verdict |
|---|---|---|---|
| **Hetzner CX33, Falkenstein** | 4 vCPU · 8 GB | ≈₹880 | **Chosen.** Double the EC2's RAM at a third the cost, no burstable-credit system |
| AWS t3.medium (current) | 2 vCPU · 4 GB burstable | ≈₹2,700–3,100 | Already paid for; a 1-year Savings Plan cuts it 30–40% with no migration |
| DigitalOcean Bangalore | 2 vCPU · 4 GB | ≈₹2,100 | Best latency, barely cheaper than AWS |
| Hetzner Singapore | 4 vCPU · 8 GB (CPX32) | ≈₹3,700 | CX series unavailable there; costs more than AWS |
| Oracle Always Free | 2 OCPU · 12 GB | ₹0 | **Rejected for production.** Oracle quietly halved the free Ampere allocation in 2026 with no announcement |

Falkenstein is ~130–160ms from India. Irrelevant for webhooks; noticeable but
acceptable for a server-rendered storefront, and Cloudflare's edge hides most
of it. Revisit only if customers complain.

## The real cost is your hours

Twenty kitchens means twenty owners messaging you when a menu won't save at
6am. Define what's included, quote anything bespoke separately, and write the
onboarding guide once. The margins above are only real if support stays
bounded.

---

# Part 3 — Architecture

## Stack

| Layer | Choice | Why |
|---|---|---|
| Framework | Django 5 | Auth, ORM, migrations, admin and templates in one box |
| Frontend | Django templates + HTMX | No SPA. Local SEO matters to a restaurant; a second frontend is a second thing to maintain per client |
| Database | Postgres | SQLite in dev until Phase 3, which needs real row locking |
| Background jobs | django-q2 or Huey + Redis | Invoice PDFs, message sends, scheduled jobs |
| PDF | WeasyPrint | An invoice template is HTML and CSS |
| Edge | Caddy, on-demand TLS | Automatic certificates for any client domain |
| WhatsApp | Meta Cloud API direct (n8n optional) | See the messaging decision below |

### Why Django rather than Next.js

Django admin gives most of the super admin for free. It is the language you are
fastest in, and this gets built on weeknights. WeasyPrint beats the JS options
for invoices. The cost is that Vercel is out — a full Django app on serverless
means 60-second ceilings, cold starts, no persistent workers and connection
exhaustion — so it runs on a container host instead.

## Tenancy

One codebase, one deployment, one database, many domains.

- Caddy terminates TLS for any domain pointed at the box; middleware reads the
  `Host` header and resolves the tenant, its config and its theme
- One Postgres database, every table carrying `tenant_id`
- **Config, never forks.** Anything that differs between kitchens is a field in
  `TenantConfig` or a key in `features`. A client's new request becomes a flag
  every client can use

### The invariant

Postgres row-level security will **not** save you — the ORM connects as an
owning role and ignores it. Isolation is enforced in application code:

```python
Order.objects.all()      # scoped to the current tenant; RAISES if none is set
Order.all_tenants.all()  # deliberately across every tenant — platform code only
```

Queries fail closed. A guard test fails the build if a model with a `tenant`
field skips scoping; opting out requires declaring
`tenant_scoping_exempt = "reason"` on the model itself.

**A cross-tenant leak is the worst bug this product can ship.** Release-blocking.

### Why not a database per client

Free-tier projects pause after a week of inactivity, have no real backups, and
every migration would run twenty times — the Annam re-import problem rebuilt at
the infrastructure layer. The client owns their domain, WABA and Razorpay
because those are theirs. The database is the product's engine.

## Messaging — the app owns the message

Full reasoning in [`adr/0001-messaging-architecture.md`](adr/0001-messaging-architecture.md).

```
service code
  └─ payloads.py       provider-agnostic content, validates Meta's limits
  └─ services.queue()  writes an OutboundMessage row  ← source of truth
  └─ worker
       └─ sender_for(tenant)
            ├─ MetaCloudSender  → Graph API           (default)
            ├─ N8nSender        → n8n webhook → Meta  (opt in, per tenant)
            └─ ConsoleSender    → the log             (development)
```

`TenantSecrets.wa_provider` picks the driver per tenant. What never moves out
of the app: what to say, validation of Meta's limits, the queue, retries,
idempotency, and the record of what happened.

A dead n8n therefore **delays** a message, never loses one.

## Suspension ladder

Encoded in `TenantStatus`, with effects already implemented on the model.

| Rung | When | Effect |
|---|---|---|
| `active` | paid | everything works |
| `past_due` | day 1–6 | owner sees a banner. **Storefront and bot untouched** |
| `restricted` | day 7–13 | backend read-only except billing. Storefront still sells |
| `suspended` | day 14+ | ordering off; menu still visible with a neutral notice. Owner keeps full access to his data |
| `cancelled` | manual only | never automatic |

Squeeze the owner before his customers. Transitions fire at 04:00 local, never
mid-service. One-click grace override. **No rung ever deletes data.**

---

# Part 4 — Data model

Every model below except the three exempt ones subclasses `TenantOwnedModel`.

```
tenancy     Tenant · TenantDomain* · TenantConfig* · TenantSecrets* · TenantUser
catalog     Slot · MenuCategory · MenuItem · MenuSchedule
delivery    DeliveryZone
content     Page · Banner
messaging   OutboundMessage
orders      Customer · Address · Order · OrderEvent · Payment · Invoice     (phase 3)
whatsapp    WaSession · WaInboundMessage                                    (phase 5)
billing     Subscription · SubscriptionInvoice · AdminAuditLog              (phase 6)
```
`*` exempt from scoping, each with a stated reason on the model.

## The two designs worth understanding

**`MenuSchedule` carries two kinds of row.** A weekday template
(`mode="weekday"`) and a dated override (`mode="date"`). Resolution looks for a
dated row first and falls back to the weekday row. That one rule gives three
behaviours from one table: weekly planning, daily planning, and a weekly
kitchen pulling one dish on one day without touching its template.
`TenantConfig.menu_mode` only decides which editor the owner sees.

**`orders.channel` is the product in one column.** Website and WhatsApp produce
identical records differing only by that value, which is why one order list, one
invoice series and one set of reports covers both. `items` and `address` are
JSON snapshots, never foreign keys — a price change next week must not rewrite
last week's bill.

---

# Part 5 — What is built

**110 tests green.** `uv run pytest -q`

| Area | State |
|---|---|
| Tenancy, fail-closed scoping, hostname routing | done |
| Super admin skeleton with suspension actions | done |
| Catalog: slots, categories, items, dual-mode scheduling | done |
| Menu resolver and slot cutoffs | done |
| Delivery zones and pincode serviceability | done |
| Storefront: home, menu, cart, CMS pages | done |
| Messaging: queue, payloads, three senders, retries, idempotency | done |
| TenantSecrets with Fernet encryption, write-only portal pattern | done |
| Orders, payments, invoices | phase 3 |
| Owner backend | phase 4 |
| WhatsApp inbound and conversation | phase 5 |
| Subscriptions and billing automation | phase 6 |
| Postgres and deploy | phase 7 |

Annam Foods is seeded as tenant #1 with three slots, nine dishes, a Mon–Sat
template (no Sunday, matching how they actually operate) and three Coimbatore
zones.

---

# Part 6 — Phases

Work in order. Each ends in something demonstrable.

| Phase | Delivers | Spec |
|---|---|---|
| 1 ✅ | Tenancy, scoping, routing | — |
| 2 ✅ | Catalog, storefront, CMS, messaging spine | — |
| 3 | **Orders, Razorpay, invoices** | [phase-3-money-path.md](phase-3-money-path.md) |
| 4 | Owner backend | [phase-4-owner-backend.md](phase-4-owner-backend.md) |
| 5 | WhatsApp inbound and conversation | [phase-5-whatsapp.md](phase-5-whatsapp.md) |
| 6 | Super admin and subscription billing | [phase-6-super-admin-billing.md](phase-6-super-admin-billing.md) |
| 7 | Postgres and production | [phase-7-production.md](phase-7-production.md) |

**Phase 3 depends on section 7a — the Postgres swap. Do that first.** Invoice
numbering needs `SELECT … FOR UPDATE` and SQLite cannot provide it.

Phases 4 and 5 can swap if you would rather prove the WhatsApp story first.
Nothing else can move.

Rough sizing, at evenings-and-weekends pace: phase 3 two weeks, phase 4 two
weeks, phase 5 a week and a half, phase 6 three days, phase 7 a few days.

## Definition of done, every phase

- `uv run pytest -q` green, covering the behaviours the phase doc lists
- `uv run python manage.py check` clean
- Migrations committed with the model changes
- The isolation tripwire still passes
- Anything kitchen-specific lives in `TenantConfig`

---

# Part 7 — Traps

Most of these are paid for already, in Annam's bug history.

**Cross-tenant leaks.** The ORM ignores RLS. One forgotten `.filter(tenant=…)`
shows one kitchen another's orders. Structure it so unscoped queries are hard
to write by accident, and keep the guard test honest.

**Meta's `cta_url` label is 20 characters.** A 26-character label silently
failed every "Place Order" tap for days. Now validated in `payloads.py` with a
boundary test. Also: one URL per message, 3 buttons, 10 list rows.

**The WhatsApp 24-hour window.** Free-form only works within 24 hours of the
customer's last message. Get four utility templates approved during onboarding
and treat approval as a provisioning step.

**Webhook idempotency.** Razorpay and Meta both retry. A duplicate that burns a
second invoice number breaks your client's invoice series — a compliance
problem in India, not an annoyance.

**Invoice numbering.** Sequential per tenant, no gaps, allocated inside a
transaction with a row lock.

**Credentials in plain text.** `ANNAM_N8N_WORKFLOWS_CLAUDECODE.md` carries a
live WhatsApp bearer token in the clear. **Rotate it.** Platform secrets go in
`TenantSecrets`, encrypted, never returned to a browser.

**Backups.** Self-hosted Postgres means they are entirely yours. Nightly
`pg_dump` to object storage plus a restore you have actually performed once.
Losing a kitchen's order history ends the relationship permanently.

**Slot cutoffs and the pincode gate.** A menu that lets someone order lunch at
2pm produces an angry phone call. Check serviceability before checkout, never
after payment.

---

# Part 8 — Open decisions

Assumptions currently in force. Correct any before the phase that depends on it.

| Question | Assumed | Needed by |
|---|---|---|
| Cash on delivery? | both, behind a per-tenant flag | phase 3 |
| Customer accounts or guest checkout? | guest, phone + OTP | phase 3 |
| OTP over SMS or WhatsApp? | undecided — WhatsApp is cheaper given the WABA | phase 3 |
| Rider assignment and tracking? | out of scope; owner marks dispatched | phase 4 |
| Menu photos — upload or migrate? | upload, with a one-time import at onboarding | phase 4 |
| GST on invoices? | schema ready, rendering in phase 6 | phase 6 |
| Tamil storefront and bot? | English first; copy in config so Tamil is a later flag | phase 6 |
| Do AVR, DHC, TailorsKart move onto this? | no — they stay on their bespoke n8n builds | — |

---

# Part 9 — Getting to the first sale

1. Phase 7a — Postgres
2. Phase 3 — a real customer pays Annam through the website
3. Phase 4 — Annam's owner runs his own menu
4. Migrate Annam off the old site: export the catalog, keep URLs where they
   matter, switch DNS at 4am on his quietest day
5. Phase 5 — WhatsApp orders land in the same list
6. Phase 6 — subscriptions and the ladder, before client #2
7. Sell

Annam is client #1 and the proving ground. Everything built before a paying
client uses it is a guess.
