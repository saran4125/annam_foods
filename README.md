# SeerKitchen

Multi-tenant ordering platform for cloud kitchens. One codebase, one database,
many kitchens — each on its own domain, differing only by configuration.

## Running it

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser     # your SEER platform login
uv run python manage.py runserver 8000
```

Then add to `/etc/hosts`:

```
127.0.0.1  annam.localhost
127.0.0.1  admin.localhost
```

- `http://annam.localhost:8000/` — a tenant storefront
- `http://admin.localhost:8000/admin/` — the SEER super admin (no tenant context)

## Adding a kitchen

```bash
uv run python manage.py provision_tenant \
  --slug annam --name "Annam Foods" \
  --domain annam.localhost \
  --owner-email owner@annamfood.in \
  --menu-mode daily
```

Onboarding a client should never be more than this plus pasting their
credentials. If it starts needing code, that's the signal something belongs in
`TenantConfig` instead.

## The one rule

Every model that belongs to a kitchen subclasses `TenantOwnedModel`. That gives
it two managers:

```python
Order.objects.all()      # scoped to the current tenant; RAISES if none is set
Order.all_tenants.all()  # deliberately across every tenant — platform code only
```

Queries fail closed. Forgetting the tenant raises `TenantContextMissing`
instead of quietly returning another kitchen's data.

Outside a web request — management commands, background jobs, tests — set the
tenant yourself:

```python
from apps.tenancy.context import tenant_context, all_tenants

with tenant_context(annam):
    Order.objects.count()        # just Annam's

with all_tenants():
    Tenant.objects.count()       # billing sweeps, the super admin
```

`test_every_tenant_owned_model_uses_the_scoped_manager` fails the build if a
model with a `tenant` field skips this. A model may opt out only by declaring
`tenant_scoping_exempt = "reason"` on itself.

## Database

Dev uses SQLite, stored at `~/.seerkitchen/dev.sqlite3` — outside the project
folder on purpose, because SQLite's locking is unreliable on synced volumes.
Moves to Postgres before Phase 3, where invoice numbering needs real row locks.

## Layout

```
config/settings/   base + per-environment settings
apps/tenancy/      tenants, domains, config, scoping, middleware
```

## Where this is going

**The whole plan is in [`docs/PLAN.md`](docs/PLAN.md).** `AGENTS.md` carries the
coding conventions; `docs/` carries the per-phase specs.

1. Foundation — tenancy, scoping, hostname routing ✅
2. Catalog, scheduling, zones, storefront, CMS pages ✅
3. Orders, Razorpay, invoices — `docs/phase-3-money-path.md`
4. Owner backend — `docs/phase-4-owner-backend.md`
5. WhatsApp — `docs/phase-5-whatsapp.md`
6. Super admin and subscription billing — `docs/phase-6-super-admin-billing.md`
7. Postgres and production — `docs/phase-7-production.md`

**Start Phase 3 by doing section 7a (the Postgres swap).** Invoice numbering
needs row locking that SQLite cannot provide.
