# AGENTS.md — read this before writing any code

SeerKitchen is a multi-tenant ordering platform for cloud kitchens. One Django
codebase, one database, many kitchens — each on its own domain, differing only
by configuration. It is sold as a subscription (₹5,000/month per kitchen), so
adding a client must never mean adding code.

**[`docs/PLAN.md`](docs/PLAN.md) is the whole plan in one file** — read it for
the why. This file is the how: the conventions and invariants you must not
break. Then work `docs/` in phase order; phases 1 and 2 are done and are the
reference for how everything else should look.

---

## Commands

```bash
uv sync                                  # install
uv run python manage.py migrate
uv run python manage.py runserver
uv run python -m pytest -q               # must be green before any commit
                                         # (python -m: console scripts break if
                                         #  the project folder is ever moved)
uv run python manage.py check
uv run python manage.py makemigrations <app>
```

Local hosts — add to `/etc/hosts`:

```
127.0.0.1  annam.localhost
127.0.0.1  admin.localhost
```

`annam.localhost` is a tenant storefront. `admin.localhost` is the SEER super
admin and deliberately carries **no** tenant.

Seed data:

```bash
uv run python manage.py provision_tenant --slug annam --name "Annam Foods" \
    --domain annam.localhost --owner-email owner@annamfood.in
uv run python manage.py seed_demo_menu --tenant annam
```

---

## The one invariant

**Every model that belongs to a kitchen subclasses `TenantOwnedModel`.**

```python
from apps.tenancy.managers import TenantOwnedModel

class Order(TenantOwnedModel):
    ...
    class Meta(TenantOwnedModel.Meta):   # note: inherit the Meta
        ...
```

That gives it two managers:

```python
Order.objects.all()      # scoped to the current tenant; RAISES if none is set
Order.all_tenants.all()  # deliberately across every tenant — platform code only
```

Queries **fail closed**. Forgetting the tenant raises `TenantContextMissing`
rather than quietly returning another kitchen's rows. Saving stamps
`tenant` automatically from context.

Outside a web request — management commands, background jobs, tests — set it
yourself:

```python
from apps.tenancy.context import tenant_context, all_tenants

with tenant_context(kitchen):
    Order.objects.count()      # just this kitchen's

with all_tenants():
    Tenant.objects.count()     # billing sweeps, super admin, cron over tenants
```

`apps/tenancy/tests/test_isolation.py::test_every_tenant_owned_model_uses_the_scoped_manager`
fails the build if a model with a `tenant` field skips this. A model may opt
out **only** by declaring `tenant_scoping_exempt = "reason"` on itself. Do not
add names to that test.

Postgres row-level security will not save you here — the ORM connects as an
owning role and ignores it. Isolation is enforced in application code, which is
why the tripwire exists. **A cross-tenant leak is the worst bug this product
can ship.** Treat it as release-blocking.

---

## Conventions

**Business logic lives in `services.py`, not in views.** The storefront, the
owner backend and the WhatsApp handler all call the same functions. If you find
yourself writing an internal HTTP endpoint so one part of the app can talk to
another, stop — make it a function.

**Views are thin.** Parse input, call a service, render. No pricing, no
availability rules, no money.

**Money is `Decimal`.** `DecimalField(max_digits=…, decimal_places=2)`. Never
float, never int-paise arithmetic scattered through the code.

**Prices are snapshotted onto orders.** Never a foreign key to the live price.
A price change next week must not rewrite last week's bill.

**Never trust a price from the client.** The cart re-prices every line from the
live menu on each render; do the same anywhere else a price appears.

**Templates are server-rendered.** Django templates, progressive enhancement.
No SPA. This is deliberate — local SEO matters to a restaurant, and a second
frontend codebase is a second thing to maintain per client.

**Messages go through `apps.messaging`, never straight to a provider.**
Build a payload with `messaging.payloads`, queue it with
`messaging.services.queue()`. The app owns content, validation, retries and
the record of what happened; the sender is a swappable driver chosen per
tenant (`TenantSecrets.wa_provider`). See `docs/adr/0001-messaging-architecture.md`.
Meta's limits — 20-character `cta_url` label, 3 buttons, 10 list rows — are
enforced in `payloads.py` and nowhere else.

**Customisation is configuration.** Anything that differs between kitchens goes
in `TenantConfig` (a field, or a key in `features`). If a client asks for
something new, it becomes a flag every client can use. Never fork per client.

**Tests are behavioural, named as sentences.** `test_dated_row_overrides_the_weekly_template`,
not `test_resolver_2`. Every phase doc lists the behaviours that must be
covered; those are the acceptance criteria.

---

## Layout

```
config/settings/       base.py + dev.py (prod.py comes in Phase 7)
apps/tenancy/          tenants, domains, config, scoping, middleware, super admin
apps/catalog/          slots, categories, items, MenuSchedule, menu resolution
apps/delivery/         zones, pincode serviceability
apps/content/          owner-written pages and banners
apps/storefront/       public site: home, menu, cart
apps/messaging/        outbound message queue, payload builders, senders
apps/orders/           customers, addresses, orders, status flow
templates/             base.html + per-app directories
static/css/            storefront.css — colours come from TenantConfig.theme
docs/                  phase specs; work them in order
```

---

## Things that must not happen

- A query that crosses kitchens without `all_tenants()`.
- A model with a `tenant` field that isn't a `TenantOwnedModel`.
- Business logic in a template or a view.
- A tenant's secrets (WhatsApp token, Razorpay key) readable by the browser, or
  committed to the repo. They go in `tenant_secrets`, encrypted, write-only
  from the portal's point of view.
- An invoice number allocated outside a transaction with a row lock.
- A price read from a form, a session, or a WhatsApp payload.
- A provider API called from anywhere but a sender in `apps/messaging/senders/`.
- A decrypted tenant secret in a response body, a log line, or the repo.
- A migration that isn't checked in alongside the model change.

---

## Current state

| Phase | Scope | Status |
|---|---|---|
| 1 | Tenancy, scoping, hostname routing, super admin skeleton | done |
| 2 | Catalog, scheduling, delivery zones, storefront, CMS pages | done |
| 3 | Orders, Razorpay, invoices — the money path | `docs/phase-3-money-path.md` |
| 4 | Owner backend | `docs/phase-4-owner-backend.md` |
| 5 | WhatsApp | `docs/phase-5-whatsapp.md` |
| 6 | Super admin and subscription billing | `docs/phase-6-super-admin-billing.md` |
| 7 | Postgres and production deploy | `docs/phase-7-production.md` |

164 tests green as of the orders app landing. Keep
them that way: a sender that can no longer decrypt a secret (rotated
`SECRETS_KEY`) must land the message `abandoned`, never leave it stuck in
`sending`.
