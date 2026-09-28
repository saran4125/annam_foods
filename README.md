# SeerKitchen

Multi-tenant ordering platform for cloud kitchens. One codebase, one database,
many kitchens — each on its own domain, differing only by configuration.

## Running it

```bash
cp .env.example .env                  # replace the example secrets
docker compose up -d postgres redis
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser     # your SEER platform login
uv run python manage.py runserver 127.0.0.1:8000
# in another terminal:
uv run python manage.py run_huey
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
  --slug example-kitchen --name "Example Kitchen" \
  --domain example.localhost \
  --owner-email owner@example.test \
  --preset daily-meals
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

Dev and production now use PostgreSQL. Docker Compose exposes development
PostgreSQL only on `127.0.0.1:5439` and Redis only on `127.0.0.1:6389`.
`scripts/migrate_local_data.sh` copies any existing
`~/.seerkitchen/dev.sqlite3` into the empty PostgreSQL database after taking
a temporary SQLite backup; it never edits or deletes the source file.
Run `uv run python -m pytest -q` and `uv run python manage.py check` after
changes. The suite uses PostgreSQL and includes a real row-lock test.

## Layout

```
config/settings/   base + per-environment settings
apps/tenancy/      tenants, domains, config, scoping, middleware
```

## Where this is going

**The whole plan is in [`docs/PLAN.md`](docs/PLAN.md)** — the single source of
truth. `AGENTS.md` carries the coding conventions.

Built: tenancy and fail-closed scoping, catalog and daily/weekly menus,
delivery zones, content pages, storefront and cart, the messaging spine,
orders, and Phase A's PostgreSQL foundation. Next, in order (PLAN.md §17):

- **A. Foundation** — complete
- **B. Bills** — billing engine, bills on WhatsApp, bill on request, catalog
  orders, owner backend v0 · *first release to Annam*
- **C. WhatsApp assistant** — the full bot in the app, parity with Annam's
- **D. Payments and updates** — Razorpay, WhatsApp Pay, every order update on
  WhatsApp
- **E. Storefront** — checkout, hero campaigns, collections, Annam's photos
- **F. Owner backend** — menus, zones, content, connections, reports
- **G. Platform** — provisioning in under an hour, subscriptions, extensions
- **H. Annam cutover**

An image-led WordPress/WooCommerce storefront prototype is running separately
on `http://annam.localhost:8090/`, with its owner editor at `/wp-admin/` and
local credentials in the ignored `wordpress/.env`. It is a review prototype;
the master plan's Django order/billing architecture does not use its catalog.
