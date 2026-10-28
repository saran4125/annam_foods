# Annam Foods

Annam Foods' website and store-management application: meals, shop products,
pincode-checked checkout, Razorpay, orders, WhatsApp inbox and billing.

The SEER platform login, kitchen picker/provisioning screens, domain-management
screens and Appearance editor were retired on **22 October 2026**. The existing
storefront design, published copy, uploaded images and business data are retained.
Use **`/manage/`** to sign in directly to Annam's admin. Billing keeps its separate
**`/billing/`** entry point using the existing staff accounts.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the current architecture and remaining
live integration/setup requirements. Older multi-kitchen roadmap documents are
historical references, not the active product scope.

## Local development

```bash
cp .env.example .env
# Replace example secrets.
docker compose up -d postgres redis
uv sync
uv run python manage.py migrate
uv run python manage.py runserver 127.0.0.1:8000
```

Add `127.0.0.1 annam.localhost` to your hosts file. Open
`http://annam.localhost:8000/` for the website and `/manage/` for admin.
An existing account must have membership in Annam or be an active superuser.
There is no public signup, SEER login or web-based tenant provisioning.

Initial installation can use the existing management command to create Annam's
store record; do not recreate it when upgrading an existing database:

```bash
uv run python manage.py provision_tenant --slug annam --name "Annam Foods" \
  --domain annam.localhost --owner-email owner@annamfood.in
```

Production defaults to `STORE_SLUG=annam`. Registered hostnames must map to that
existing store. Development without `STORE_SLUG` can exercise the retained scoped
models in isolation tests; it does not restore the retired platform routes.

## Store management

- `/manage/`: direct admin login/dashboard.
- `/manage/orders/`: website/manual/WhatsApp orders and fulfilment.
- `/manage/whatsapp/`: conversation inbox.
- `/manage/whatsapp/settings/`: phone-number ID and encrypted n8n sync token.
- `/manage/payments/razorpay/`: owner-only test/live payment settings.
- `/manage/checkout-settings/`: Tamil Nadu shop delivery, fees, minimums and meal closures. Shop delivery has no pincode whitelist; meal pincodes remain mandatory.
- `/manage/billing/`: shared legal/tax settings.
- `/manage/settings/`: existing store settings.
- Dishes & products opens Meals with Breakfast/Lunch/Dinner groups; Other items
  keeps shop products separate. Unscheduled meals appear under Not assigned.
  Choose the actual menu date, then **Choose dishes** and save that meal's menu.
  Saved date menus are independent: removing a dish does not delete its product
  or change another date. Empty saved menus stay empty. **All dishes** opens the
  underlying catalog/recurring schedules. Imported menus need staff review; new
  imports no longer guess seven-day availability from source category labels.
- Categories, meal times, banners, pages and delivery areas remain editable.
- `/billing/`: separate manual, website and WhatsApp billing screens.

Old Annam workspace management/billing/preview GET bookmarks redirect to the
corresponding local tools or website. Old SEER login GET links redirect to
`/manage/login/`. Removed domain/editor/provisioning pages return 404; old POST
operations are not replayed into a different endpoint.

## Payment and messaging setup

The Razorpay integration verifies signed callbacks/webhooks and fetched provider
state before recording capture. It supports private customer receipts/bills,
live invoice issuance and owner-only full refunds. **A real sandbox payment still
needs Annam's keys, public webhook configuration and end-to-end testing.** See
[docs/razorpay.md](docs/razorpay.md).

Keep the existing n8n automation. Connect incoming, outgoing and status-copy nodes
to the inbox using [docs/n8n/inbox-sync.md](docs/n8n/inbox-sync.md). Mirroring does
not automatically create a billable order; staff can create a WhatsApp booking.
Live n8n sync needs verification. Automatic WhatsApp bill delivery is separate work.

The existing `/platform/webhooks/annam/...` integration URLs and
`/platform/assets/annam/...` published-image URLs remain for compatibility.
These technical paths do not provide a SEER platform interface.

## Deployment and storage

`build.sh` installs dependencies and collects static files. `start.sh` applies
migrations and supervises Gunicorn plus the database inbox worker. `render.yaml`
is the free demo configuration; `render.paid.yaml` defines durable disk/database
infrastructure. Actual infrastructure and plan activation remain external.

Keep database IDs, `SECRET_KEY` and `SECRETS_KEY` unchanged when upgrading. No
schema migration/data deletion is required for the Annam-only conversion.
Published editor images remain in PostgreSQL. Legacy catalog/banner uploads still
need durable public storage; `/tmp` on the free service is ephemeral.

Optional background processes:

```bash
uv run python manage.py run_whatsapp_worker
uv run python manage.py run_huey
uv run python manage.py reconcile_razorpay
```

The Render supervisor already runs the inbox worker. Huey/Redis and periodic
payment reconciliation require separate deployment if used. Configure the latter
with an external scheduler; the command does not create a charge or refund.

## Engineering invariants and checks

Retained tenant foreign keys/managers protect existing records and financial
history; removing the platform UI does not justify dropping isolation. Missing
context fails closed. Shared services own pricing/business rules. Money uses
Decimal and orders/invoices retain their original snapshots. Secrets are encrypted
and never returned in forms/logs. See [AGENTS.md](AGENTS.md).

```bash
uv run python -m pytest -q
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

The separate `wordpress/` prototype is not the Django storefront/order database.
Git history preserves the previous SEER implementation if it is ever needed for
review; it is no longer the active application experience.

Current ordering, delivery, courier and reporting rules: [implementation and staff workflow](docs/ordering-delivery-requirements.md).
