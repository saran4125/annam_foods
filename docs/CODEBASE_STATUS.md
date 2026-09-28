# SeerKitchen codebase status

Last reviewed: 28 September 2026  
Repository: `/Users/sudhan/Desktop/SEER/CloudKitchen`

This document is a current-state inventory of the repository and local development
data. It complements `PLAN.md`, which describes the intended product and future
phases. Secrets and encrypted credential values are deliberately excluded.

## 1. Executive summary

SeerKitchen is a server-rendered Django multi-tenant ordering platform for cloud
kitchens. One deployment and database serve many kitchens, with hostname-based
tenant resolution and configuration-driven branding.

Implemented today:

- fail-closed tenant scoping and hostname routing;
- tenant configuration and encrypted provider credentials;
- catalog, meal slots, weekly schedules and dated overrides;
- delivery-zone and pincode serviceability;
- CMS pages and promotional banners;
- tenant storefront, live-priced session cart and pincode checking;
- provider-independent outbound messaging with Meta, n8n and console senders;
- an Annam-specific storefront configuration with three promotional hero slides,
  Annam branding, and a food-category showcase.

Implemented since the 20 September review:

- durable customers, addresses, orders and an order-event audit trail, with
  `orders.services.create_order` as the single entry point for every channel.

Not implemented yet:
- checkout, OTP and Razorpay payments;
- invoice allocation and PDF generation;
- owner operations backend;
- inbound WhatsApp conversations;
- subscription billing;
- PostgreSQL and production deployment.

The project is therefore a functional storefront/catalog foundation, not yet a
complete transactional ordering system.

## 2. Non-negotiable architecture rules

1. Every kitchen-owned model subclasses `TenantOwnedModel`.
2. `Model.objects` is tenant-scoped and raises `TenantContextMissing` without a
   tenant context.
3. Cross-tenant platform work must explicitly use `all_tenants()` or the
   `all_tenants` manager.
4. Business logic belongs in services, not templates or views.
5. Money uses `Decimal`/`DecimalField`, never floating point.
6. Client-provided prices are never trusted; menu and cart prices are resolved
   from live server-side catalog data.
7. Tenant differences are configuration, never client-specific forks.
8. Provider calls go through `apps.messaging` senders.
9. Tenant secrets are encrypted at rest and never rendered back to a browser.

## 3. Runtime and dependencies

| Area | Current value |
|---|---|
| Language | Python 3.10+ |
| Framework | Django 5.x |
| Development database | SQLite at `~/.seerkitchen/dev.sqlite3` |
| Production database | Planned PostgreSQL; not configured |
| Rendering | Django templates and CSS |
| Image handling | Pillow / Django `ImageField` |
| Markdown pages | Python-Markdown |
| Secret encryption | Fernet via `cryptography` |
| Test runner | pytest + pytest-django |
| Dependency manager | `uv` expected by documentation |

Direct dependencies from `pyproject.toml`:

- `django>=5.0,<6.0`
- `cryptography>=50.0.1`
- `markdown>=3.10.3`
- `pillow>=12.3.0`
- `python-dotenv>=1.0`
- development: `pytest>=8.0`, `pytest-django>=4.8`

## 4. Application inventory

### `apps.tenancy`

Purpose: tenant identity, hostname routing, configuration, membership, encrypted
credentials and fail-closed ORM scoping.

Models:

| Model | Important fields and behavior |
|---|---|
| `Tenant` | slug, name, primary domain, status; exposes ordering and backend-access properties |
| `TenantDomain` | globally resolvable hostname; intentionally exempt from tenant scoping |
| `TenantConfig` | brand, theme, timezone, menu mode, hours, invoice series, GST/FSSAI and feature flags |
| `TenantUser` | user-to-tenant membership and owner/manager/staff role |
| `TenantSecrets` | encrypted WhatsApp, n8n and Razorpay credentials; one-to-one with tenant |

Tenant statuses: `provisioning`, `active`, `past_due`, `restricted`, `suspended`,
and `cancelled`.

Key files:

- `context.py`: context variables, `tenant_context()` and `all_tenants()`.
- `managers.py`: scoped manager and `TenantOwnedModel`.
- `middleware.py`: maps request hostnames to tenants.
- `crypto.py`: Fernet encryption/decryption and masking.
- `forms.py`: write-only secret-editing behavior.
- `adminbase.py`: deliberate unscoped admin access.
- `provision_tenant.py`: creates a tenant, domain, configuration, secrets and owner.

### `apps.catalog`

Purpose: meal slots, products and date/weekday menu planning.

Models:

| Model | Important fields and behavior |
|---|---|
| `Slot` | key, label, cutoff, delivery window, ordering and active flag |
| `MenuCategory` | name, ordering and active flag |
| `MenuItem` | category, description, Decimal price, image, vegetarian flag, tags and active flag |
| `MenuSchedule` | weekday/date mode, availability, stock limit/sold count and optional price override |

Menu resolution checks a dated schedule first and falls back to its weekday
template. Dated rows can remove or reprice one dish without changing the weekly
plan.

Management commands:

- `seed_demo_menu`: seeds three slots, nine demo dishes, Monday-Saturday
  schedules and three Coimbatore zones.
- `import_menu_images`: safely matches image filenames to dish names, reporting
  ambiguous and unused files instead of guessing.

### `apps.delivery`

Purpose: delivery serviceability.

`DeliveryZone` stores pincode, area, delivery fee, minimum order and optional
slot restrictions. `zones_for_pincode()` normalizes human-entered pincodes and
returns active zones within the current tenant.

### `apps.content`

Purpose: owner-managed pages and storefront promotions.

| Model | Use |
|---|---|
| `Page` | Markdown content, SEO description, publication and navigation controls |
| `Banner` | promotional title, subtitle, image, link, active flag and display order |

The current home template slices the first three active banner records and then
checks whether each has an image; this is not equivalent to selecting the first
three valid images. The promotional rail separately reuses records at positions
2–4, so hero and promotional content can duplicate. See
[OPENCODE_STOREFRONT_HANDOFF.md](OPENCODE_STOREFRONT_HANDOFF.md) for the pending fixes
and complete owner-editable storefront specification.

### `apps.storefront`

Purpose: public tenant website.

Routes:

| Method/path | View | Purpose |
|---|---|---|
| `GET /` | `home` | promotions, food showcase, featured menu and slots |
| `GET /menu/` | `menu` | today/tomorrow and slot-specific live menu |
| `GET /cart/` | `cart_detail` | repriced cart, delivery zone and totals |
| `POST /cart/add/` | `cart_add` | add/remove a quantity |
| `POST /cart/pincode/` | `cart_set_pincode` | select delivery serviceability |
| `GET /p/<slug>/` | `page_detail` | published CMS page |

The cart is session-backed. It stores item IDs and quantities but recomputes
prices through `resolve_menu()` on every read. Changing meal slot or day clears
the cart so products cannot cross incompatible menus.

Current storefront composition:

- orange announcement strip;
- Annam logo and primary navigation;
- breakfast/lunch/dinner category navigation;
- three-image, image-only promotional slider with arrows, dots and automatic
  rotation;
- configured Annam food-category image rail;
- best-seller/product grid;
- meal-slot summaries;
- ordering explanation and closing call-to-action;
- responsive menu and cart pages.

### `apps.messaging`

Purpose: persist outbound messages before attempting provider delivery.

`OutboundMessage` records recipient, provider-independent JSON payload, purpose,
status, provider, attempts, errors, next attempt, deduplication key and timestamps.

Supported payloads:

- text;
- reply buttons;
- CTA URL;
- list message;
- document;
- template.

Supported senders:

- Meta Cloud API;
- n8n webhook;
- development console.

The worker retries transient failures and abandons permanent failures. A sender
exception, including failure to decrypt after a key rotation, is recorded as
`abandoned` rather than leaving the message stuck in `sending`.

## 5. Local development data snapshot

Snapshot source: `~/.seerkitchen/dev.sqlite3` on 20 September 2026.

### Tenant

| Field | Value |
|---|---|
| ID | 1 |
| Slug | `annam` |
| Name | Annam Foods |
| Primary domain | `annam.localhost` |
| Status | `active` |
| Menu mode | `daily` |
| Timezone | `Asia/Kolkata` |
| Currency | `INR` |
| Invoice prefix / next number | `INV` / 1 |

### Brand configuration

| Token | Value |
|---|---|
| Primary color | `#FF8507` |
| Dark color | `#1C1C1C` |
| Surface | `#FDFCFB` |
| Text | `#010101` |
| Logo | Annam CDN logo URL stored in `TenantConfig.theme.logo_url` |

The `food_showcase` feature contains six Annam categories: Podi, Snacks, Chips,
Sweets, Pickles and Ghee. Their images currently reference Annam's existing CDN.

### Meal slots

| Slot | Order cutoff | Delivery window |
|---|---:|---|
| Breakfast | 09:00 | 07:30-09:30 |
| Lunch | 11:00 | 12:30-14:00 |
| Dinner | 19:00 | 19:30-21:30 |

### Demo menu

| Item | Price | Vegetarian |
|---|---:|---|
| Idly (4) | ₹40 | Yes |
| Pongal | ₹60 | Yes |
| Masala Dosa | ₹70 | Yes |
| Veg Meals | ₹120 | Yes |
| Chicken Biryani | ₹180 | No |
| Curd Rice | ₹60 | Yes |
| Chapati (3) | ₹70 | Yes |
| Parotta (2) | ₹80 | Yes |
| Egg Fried Rice | ₹110 | No |

These are explicitly demo records and should not be treated as Annam's approved
production catalogue. None currently has a menu-item image attached.

### Delivery zones

| Pincode | Area | Fee | Minimum |
|---|---|---:|---:|
| 641001 | RS Puram | ₹20 | ₹150 |
| 641002 | Gandhipuram | ₹30 | ₹150 |
| 641038 | Peelamedu | ₹40 | ₹200 |

### Promotional banners

| Order | Title | Image | Link |
|---:|---|---|---|
| 0 | Krishna Jeyanthi | `banners/hero-festival.jpg` | `/menu/` |
| 1 | Today's Breakfast | `banners/hero-breakfast.jpg` | `/menu/?slot=breakfast` |
| 2 | Today's Lunch | `banners/hero-lunch.jpg` | `/menu/?slot=lunch` |

### Row counts

| Table/domain | Rows |
|---|---:|
| Slots | 3 |
| Menu categories | 1 |
| Menu items | 9 |
| Menu schedules | 54 |
| Delivery zones | 3 |
| CMS pages | 0 |
| Banners | 3 |
| Outbound messages | 0 |
| Tenant users | 1 |

## 6. Templates and static assets

| File | Responsibility |
|---|---|
| `templates/base.html` | document shell, tenant theme tokens, header, footer and script blocks |
| `templates/storefront/home.html` | hero slider, food categories, products, slots and promotional content |
| `templates/storefront/menu.html` | day/slot selector and menu-item ordering cards |
| `templates/storefront/cart.html` | quantities, pincode, totals and checkout blocking reasons |
| `templates/storefront/page.html` | owner-written CMS page |
| `static/css/storefront.css` | complete mobile-first visual system and responsive layout |

Media is stored under `media/` in development and is intentionally ignored by
Git. Production object storage has not been implemented.

## 7. Test coverage

Test modules cover:

- tenant scoping, missing-context failure and model-manager tripwire;
- middleware hostname behavior;
- secret encryption, masking and write-only admin forms;
- catalog resolution, dated overrides, availability, stock and cutoffs;
- database schedule constraints;
- image-import matching and ambiguity handling;
- pincode normalization, serviceability and tenant isolation;
- storefront brand/menu/cart/suspension/CMS behavior;
- banner-to-hero rendering;
- payload validation and Meta platform limits;
- message persistence, retrying, abandonment, deduplication and tenant isolation;
- Meta/n8n/console sender behavior.

The last successful full run during storefront work was **125 passing tests**.
The current session could not repeat the run because `uv` is not installed and
the existing local `.venv` points at an incompatible interpreter. The source has not
been represented here as currently green until that environment is repaired.

## 8. Current Git working tree

The working tree is not clean. It contains the recent storefront redesign,
messaging robustness work, documentation updates and image-import command.

Modified tracked areas include:

- root documentation and ignore rules;
- messaging senders, services and tests;
- storefront views, templates, CSS and tests;
- storefront template filters;
- documentation indexes.

Untracked source/documentation files include:

- `apps/catalog/management/commands/import_menu_images.py`;
- `apps/catalog/tests/test_image_import.py`;
- `docs/PLAN.md`;
- `docs/storefront-redesign.md`;
- this status document.

These changes should be reviewed and committed as coherent units before Phase 3.

## 9. Known risks and technical debt

### Release blockers before taking payments

1. PostgreSQL is required before invoice-number allocation and concurrent payment
   processing. SQLite does not provide the required row locking.
2. The payments application does not exist. Orders do (`apps/orders`);
   invoice-number allocation still waits on PostgreSQL.
3. Razorpay webhook verification and idempotency do not exist.
4. Checkout is deliberately disabled.
5. Production settings, storage, background workers, TLS/deployment definitions
   and backup/restore processes do not exist.

### Storefront/content risks

1. The three hero images live in ignored local `media/`; they will not be
   available in a fresh clone or deployment until object storage or a deployment
   media process is configured.
2. Logo and food-showcase images use remote Annam CDN URLs. An upstream URL change
   would break them, and production should copy approved assets to owned storage.
3. The hero slider assumes active banners contain images. Image-less banners can
   make navigation-dot counts disagree with rendered slides.
4. Desktop and mobile use the same hero image. A dedicated mobile crop is not
   represented in the current `Banner` model.
5. The demo menu conflicts with Annam's described vegetarian/Brahmin positioning;
   it includes Chicken Biryani and Egg Fried Rice. Production data must be replaced.
6. Menu-item photography is still missing even though the category showcase has
   imagery.

### Backend/concurrency risks

1. `dispatch_pending()` reads due messages without atomically claiming them.
   Multiple workers could deliver the same row concurrently. PostgreSQL row
   locking with `select_for_update(skip_locked=True)` or an atomic claim is needed.
2. Tenant-scoped managers protect reads but do not themselves prove that every
   foreign-key relation points to an object from the same tenant. Services should
   validate cross-model tenant consistency, especially for future orders.
3. `TenantConfig.features` is intentionally flexible JSON but lacks schema
   validation for storefront keys such as `food_showcase`.

### Development environment

1. Documentation expects `uv`, but `uv` is unavailable on the current host.
2. The existing `.venv` contains stale/incompatible interpreter paths and a
   compiled `cryptography` binary that cannot load on the current Python runtime.
3. Development server processes have previously used `--noreload`, causing stale
   templates and CSS to remain visible until restart.

## 10. Recommended next actions

1. Recreate the development environment with `uv` and establish a fresh green
   test run.
2. Review and commit the current storefront/messaging changes.
3. Move development and CI to PostgreSQL as specified in Phase 7a.
4. Replace demo Annam menu data with client-approved items, prices, dietary flags
   and photography.
5. Move hero, logo and food imagery into owned/object storage and add mobile hero
   crops.
6. Add banner validation and an owner-friendly promotion editor.
7. Implement Phase 3 in service-first order: models, order creation, payment
   verification, invoice allocation, then checkout UI.
8. Make the messaging worker claim rows atomically before running more than one
   worker.

## 11. Repository file inventory

### Root and configuration

- `AGENTS.md`
- `README.md`
- `manage.py`
- `pyproject.toml`
- `uv.lock`
- `config/urls.py`
- `config/wsgi.py`
- `config/settings/base.py`
- `config/settings/dev.py`

### Tenancy

- `apps/tenancy/admin.py`
- `apps/tenancy/adminbase.py`
- `apps/tenancy/apps.py`
- `apps/tenancy/context.py`
- `apps/tenancy/crypto.py`
- `apps/tenancy/forms.py`
- `apps/tenancy/managers.py`
- `apps/tenancy/middleware.py`
- `apps/tenancy/models.py`
- `apps/tenancy/management/commands/provision_tenant.py`
- `apps/tenancy/migrations/0001_initial.py`
- `apps/tenancy/migrations/0002_tenantsecrets.py`
- tenancy test modules: isolation, middleware, secrets and secret admin forms

### Catalog and delivery

- `apps/catalog/admin.py`
- `apps/catalog/apps.py`
- `apps/catalog/models.py`
- `apps/catalog/services.py`
- `apps/catalog/management/commands/seed_demo_menu.py`
- `apps/catalog/management/commands/import_menu_images.py`
- `apps/catalog/migrations/0001_initial.py`
- catalog tests: constraints, menu resolver and image import
- `apps/delivery/admin.py`
- `apps/delivery/apps.py`
- `apps/delivery/models.py`
- `apps/delivery/services.py`
- `apps/delivery/migrations/0001_initial.py`
- `apps/delivery/tests/test_zones.py`

### Content and storefront

- `apps/content/admin.py`
- `apps/content/apps.py`
- `apps/content/models.py`
- `apps/content/migrations/0001_initial.py`
- `apps/storefront/apps.py`
- `apps/storefront/cart.py`
- `apps/storefront/urls.py`
- `apps/storefront/views.py`
- `apps/storefront/templatetags/storefront_extras.py`
- `apps/storefront/tests/test_storefront.py`
- all templates and `static/css/storefront.css` listed in section 6

### Messaging

- `apps/messaging/admin.py`
- `apps/messaging/apps.py`
- `apps/messaging/models.py`
- `apps/messaging/payloads.py`
- `apps/messaging/services.py`
- `apps/messaging/senders/base.py`
- `apps/messaging/senders/console.py`
- `apps/messaging/senders/meta_cloud.py`
- `apps/messaging/senders/n8n.py`
- `apps/messaging/management/commands/send_pending_messages.py`
- `apps/messaging/migrations/0001_initial.py`
- messaging tests: payloads, dispatch and senders

### Documentation

- `docs/README.md`
- `docs/PLAN.md`
- `docs/storefront-redesign.md`
- `docs/phase-3-money-path.md`
- `docs/phase-4-owner-backend.md`
- `docs/phase-5-whatsapp.md`
- `docs/phase-6-super-admin-billing.md`
- `docs/phase-7-production.md`
- `docs/adr/0001-messaging-architecture.md`
- `docs/n8n/wa-send-workflow.md`
- `docs/CODEBASE_STATUS.md`

Empty package `__init__.py` files are present throughout the Python packages and
migration/management/test directories and are omitted from the detailed lists.
