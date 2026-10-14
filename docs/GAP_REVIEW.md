# SeerKitchen — gap review against PLAN.md

**Reviewed 6 October 2026** · commit `5681694` plus the three uncommitted files
(`AGENTS.md`, `apps/messaging/services.py`, `docs/CODEBASE_STATUS.md`).

This is a work list for the next coding session. Section numbers (§) refer to
[`PLAN.md`](PLAN.md). Fix Part 1 first, then start Phase B (Part 3).

How it was checked: the repository was cloned at this commit, the uncommitted
changes applied, and the suite run on a fresh PostgreSQL 16 — **189 passed**,
`manage.py check` clean, no missing migrations. Items marked *(tested)* were
confirmed with a throwaway test; items marked *(read)* come from reading the
code.

---

## Summary

| | |
|---|---|
| Phase A — Foundation | **Done**, with the defects in Part 1 |
| Phases B–H — bills, WhatsApp, payments, checkout, owner backend, platform, cutover | **Not started** |
| Off-plan work | A WordPress/WooCommerce storefront prototype in `wordpress/` (Part 2) |
| Annam's main problem (bills, bill on request, bills on WhatsApp) | **Nothing built yet** — only the billing settings table exists |

Roughly one week of the plan's twelve is complete.

### Requirements (PLAN.md §1)

| # | Requirement | State | What exists / what's missing |
|---|---|---|---|
| R1 | Website with owner login, checkout, WhatsApp ordering | partial | Menu and cart work. No checkout, no owner login, no WhatsApp ordering |
| R2 | Website and WhatsApp share one order book and billing | partial | One `Order` model with `channel`/`source`. Nothing creates orders from either channel yet |
| R3 | **Invoicing; bill on request** | **missing** | No invoice models, numbering, PDF or request flow |
| R4 | Bills and payments on WhatsApp | missing | Outbound queue exists; no document sending, no payments |
| R5 | Order updates on WhatsApp | missing | No notifications module |
| R6 | WhatsApp parity with Annam's bot | missing | No inbound webhook, no conversation engine |
| R7 | Bill to owner and customer | missing | — |
| R8 | Plug and play | partial | Flag registry, two presets, provisioning command. No copy keys, keyword lists, extensions, theme overrides |
| R9 | Cloud kitchens only, one common solution | ok | — |
| R10 | Festival, cashback, refund pages the owner edits | partial | Pages exist; editable only in the super admin. Presets lack the cashback and festival pages |
| R11 | Daily or weekly menu | built | Editable only in the super admin |
| R12 | WhatsApp and Razorpay set up in the owner login | partial | Encrypted, write-only secrets in the super admin. No owner Connections page, no test buttons |
| R13 | Super admin can switch off a non-paying kitchen | partial | Manual status actions work. No subscriptions, no automatic ladder |
| R14 | Cost targets | n/a | — |
| R15 | Python app owns the logic | at risk | True for Django; the WordPress prototype is a second system (Part 2) |
| R16 | Sweet Karam look, Annam model and photos | partial | Django product grid. Annam's 328 photos were fetched into WordPress only |
| R17 | Image-only hero, three managed slides | partial | Hero renders up to three banners. No mobile image, no start/end dates, no promo placement, no owner editor |

---

## Part 1 — Fix now (defects in what is built)

Each item: what is wrong, where, what to do, and the test that proves it.

### G1 · Saving a kitchen's settings can crash the super admin *(tested)*
- **Where:** `apps/tenancy/features.py::validate_features`, `apps/tenancy/models.py::TenantConfig.clean`, `apps/storefront/views.py::home`.
- **Wrong:** `validate_features` rejects any key not in the registry by raising a plain `ValueError`. Django forms only catch `ValidationError`, so the admin returns a 500. The home page reads `config.features["food_showcase"]`, which is not a flag — so any kitchen that has it (Annam does, per `CODEBASE_STATUS.md`) can no longer be saved.
- **Do:** move `food_showcase` out of `features` into its own field (e.g. `TenantConfig.home_sections`, JSON) with a data migration; read it from there in the view. Make `clean()` raise `ValidationError`. `features` then holds registry flags only.
- **Test:** a config carrying the old key migrates cleanly; `full_clean()` on an unknown flag raises `ValidationError`; the admin change form for a tenant with a showcase saves with 200/302.

### G2 · One kitchen without settings stops scheduled work for every kitchen *(tested)*
- **Where:** `apps/jobs/services.py::due_local_kitchens`, `send_due_messages`; `Tenant.feature`.
- **Wrong:** both loops read `tenant.config`; a tenant created without a `TenantConfig` raises and the loop ends — no messages go out for any kitchen that minute, every minute. `tenant.feature()` raises the same way.
- **Do:** guarantee a config exists (create it with the tenant, plus a data migration for existing rows), and make each loop iteration independent: catch, log with the tenant slug, continue. Skip suspended and cancelled tenants where the job is customer-facing.
- **Test:** with one broken and one healthy tenant, the healthy one is still processed and the failure is logged.

### G3 · A message can stay in "sending" forever *(read)*
- **Where:** `apps/messaging/services.py::deliver`, `dispatch_pending`.
- **Wrong:** the row is committed as `SENDING` before the provider call. If the worker dies before the final save, nothing ever picks it up again (`is_deliverable` is only `PENDING`/`FAILED`). The plan's promise is "a dead provider delays a message; it never loses one" (§5.5).
- **Do:** record `claimed_at`; in `dispatch_pending`, return rows stuck in `SENDING` for more than 5 minutes to `FAILED` with a note and normal back-off (attempt cap still applies).
- **Test:** a row left in `SENDING` with an old `claimed_at` is retried; a fresh one is not.
- Also commit the uncommitted row-lock change in `deliver` — it is correct — and add a two-thread test for it.

### G4 · Billing settings disagree with the plan and live in two places *(tested)*
- **Where:** `apps/tenancy/models.py::BillingProfile`, `TenantConfig`.
- **Wrong:** defaults are tax 0%, SAC blank, round-off off, delivery fee untaxed, 4-digit number. The plan (§8.5, §8.10, §21) says 5%, `996331`, round-off on, delivery fee taxed, `{prefix}/{fy}/{seq}` padded to 5 (`AF/26-27/00012`). `TenantConfig` still carries `invoice_prefix`, `invoice_next_no`, `gstin`, `fssai_no` — a second copy of GSTIN/FSSAI, and a plain counter that is exactly the unsafe numbering §8.5 replaces.
- **Do:** make `BillingProfile` the single source: add `invoice_prefix` there, copy values across in a data migration, remove the four `TenantConfig` fields. Fix the defaults. Add the missing settings Phase B needs: `bill_timing` (`on_payment`/`on_delivery`), `bill_request_promise_hours` (24), `bill_request_daily_limit` (5). Validate on save that the worst-case number is ≤ 16 characters and uses only letters, digits, `-` and `/`.
- **Test:** defaults match the plan; an over-long or illegal format is rejected with a clear message.

### G5 · Tests write photos into the real `media/` folder *(tested)*
- **Where:** `apps/catalog/tests/test_image_import.py`.
- **Wrong:** every run leaves four files in `media/menu/` (96 so far on the dev machine).
- **Do:** an autouse fixture that points `MEDIA_ROOT` at `tmp_path`. Delete the leftover `veg-meals_*.jpg` / `idly_*.png` files.

### G6 · `PLAN.md` §4.1 table is broken *(read)*
- §4.2 was inserted in the middle of the defects table; rows D5 and D6 now sit under the §4.2 paragraph. Move §4.2 below the table.

### G7 · Delete `apps/storefront/tests/test_zzdiag.py`
- A leftover debugging script committed by mistake. It asserts nothing and derives times from the wall clock, against §18 rule 1.

### G8 · Production settings are not deployable yet *(read)*
- **Where:** `config/settings/base.py`, `prod.py`.
- **Wrong:** `PLATFORM_HOST` is hard-coded to `admin.localhost`, so the super admin is unreachable in production. No static-file serving, no log/error reporting, no media storage setting (public vs private bucket, §16), no `/healthz`.
- **Do:** read `PLATFORM_HOST` from the environment (required in prod); add WhiteNoise or a Caddy static route; `LOGGING` with errors to email/stderr; `STORAGES` for public media and private bills; a `/healthz` view. Needed before Phase B's "deploy to production".

### G9 · Smaller mismatches
- `TenantConfig.bot_idle_reset_hours` defaults to 24; the plan says 12 (§7.4).
- Presets (§6.3) should ship draft **delivery-cashback** and **festival-offer** pages as well as about and refund policy (R10).
- The preset test should also load the provisioned kitchen's home page (§6.6).
- The no-slug guard only looks for quoted `annam` in `.py` files. Extend it to templates and `static/`, and take the forbidden list from the tenant slugs in fixtures rather than one literal.
- None of the 16 flags is read anywhere yet. That is expected for unbuilt features, but `website_ordering` should already gate add-to-cart. Rule going forward: a feature is not done until its flag is read and tested in both states.
- `create_order` still requires a slot and date and never sets `fulfilment`; courier orders cannot be created. `Order.external_ref` has no uniqueness, so a redelivered catalog webhook could create a second order. Both are needed for Phase B catalog orders — add a unique constraint on `(tenant, external_ref)` where not blank.
- Commit the three uncommitted files.

---

## Part 2 — Decision needed: the WordPress prototype

`wordpress/` is a separate WooCommerce Multisite with its own catalog, carts and
MariaDB. Checkout is disabled. `PLAN.md` §4.2 already says a choice must be made
before anything transactional is connected.

Recommended: **keep Django as the product, treat WordPress as a look-and-feel
reference, and reuse its data.**

- Write a Django management command that imports `wordpress/data/catalog.json`
  and its downloaded photos into `MenuCategory` / `MenuItem` (with
  `fulfilment="courier"` for snacks and sweets), dry-run first.
- Carry the visual decisions in `wordpress/reports/UI_REVIEW.md` into the Django
  templates in Phase E.
- Stop adding to `wordpress/`. Move the 12 MB of generated artwork out of git
  (keep it in object storage or Git LFS).

If WordPress is chosen instead, §5, §8, §10 and §17 of the plan must be
rewritten first — the order book, billing and WhatsApp flows all assume Django.

---

## Part 3 — Not built yet, in build order

Tick these off against PLAN.md §17. Nothing below has been started unless noted.

### Phase B — Bills (first release to Annam) · §7.2, §7.5 B, §7.9, §7.10, §8
- [ ] `apps/billing`: `InvoiceSequence`, `Invoice`, `InvoiceRequest`; gapless numbering under `select_for_update`; financial-year rollover; credit-note series
- [ ] Three tax modes (Tax Invoice / Bill of Supply / Bill); §8.10 calculation; amount in words; snapshots of seller and buyer; issued bills immutable
- [ ] PDF (A4 and 80 mm) rendered on the worker, stored privately
- [ ] `apps/whatsapp` inbound webhook: signature check, dedupe on `wamid`, status updates, `WaInboundMessage`, **legacy forward to n8n**; `TenantSecrets.inbound_adapter` and `legacy_forward_url`
- [ ] Catalog `order` messages → orders, re-priced by `retailer_id`
- [ ] "bill" in chat → order list → PDF; "not listed" → `InvoiceRequest`; Swiggy/Zomato answer; GST details with GSTIN checksum; `Customer.gstin`, `business_name`, `billing_address`
- [ ] Document sending through Meta media upload; `send_or_template`; `bill_ready` and `order_confirmed` templates
- [ ] Owner alerts and commands `PAID`, `BILL`, `ORDERS` (with `YES` confirmation)
- [ ] Owner backend v0 at `/manage/`: WhatsApp OTP login (`OtpChallenge`), Today, Orders, Quick bill, mark paid, Bill requests, Bills list and export, Billing settings with preview
- [ ] Production deployment (G8 first)
- [ ] The 13 billing acceptance tests in §8.14

### Phase C — WhatsApp assistant · §7.3, §7.4, §7.5 A, §7.11, §7.12
- [ ] Pure conversation engine and action executor; `WaSession`
- [ ] All 26 parity rows in §7.3; guided ordering; snacks branch; seasonal `Collection` with keywords; kitchen-closed notice; contact fallback; hand-off
- [ ] Inbox with take over / resume; `BotCopy`, `KeywordSet`; `Address.lat/lng`
- [ ] Forwarded events reach zero → retire Annam's n8n flows

### Phase D — Payments and updates · §7.7, §7.8, §9
- [ ] `apps/payments`: `Payment`, `PaymentEvent`, `Refund`; Razorpay links, webhook with signature + fetch + idempotency; reminder at 20 min, expiry at 60; reconciliation job
- [ ] COD; refunds with credit notes
- [ ] `notifications.on_order_event` — every row of §7.8 with dedupe keys and template fallback
- [ ] Native WhatsApp Pay behind its flag

### Phase E — Storefront · §10
- [ ] `/checkout/`, `/order/<no>/` with Download bill, `/track/`, `/c/<slug>/`, `/collections/<slug>/`, `/item/<id>/`
- [ ] `Campaign` replacing `Banner` (desktop + mobile art, dates, placements); promo tiles
- [ ] `MenuCategory` slug/image/description; `MenuItemImage`; Annam's photos in our storage (D5)
- [ ] Catalog sync to Meta behind its flag

### Phase F — Owner backend · §11
- [ ] Menu editors (day/week, copy yesterday, sold out), CSV import, photos
- [ ] Zones and `ShippingRule`; content editor; copy and keyword editors; notification toggles
- [ ] Connections page with write-only secrets and test buttons (R12)
- [ ] Customers, reports with WhatsApp message counts and cost; full owner command set

### Phase G — Platform · §6.5, §12
- [ ] Provisioning wizard; template pack submission and status (`WaTemplate`)
- [ ] `Subscription`, UPI autopay, suspension ladder job, impersonation, `AdminAuditLog`
- [ ] Extensions: `ExtensionConfig`, `event_webhook`, `sheets_export`, `group_tracking`

### Phase H — Annam cutover · §19
- [ ] Staging review, DNS move, redirects, backups rehearsed, token rotation

### Scheduled jobs (§14) — 2 of 9 exist
Built: send pending messages, daily 04:00 handoff (records the day only).
Missing: payment reminders and expiry, payment reconciliation, menu roll and
catalog sync, owner morning summary, billing ladder, template status refresh,
session expiry, message pruning.

---

## Still waiting on people, not code (§21)

- Annam's accountant: GST mode, rate, SAC, delivery-fee treatment, prices inclusive or not.
- Annam: bill prefix, owner phone numbers, bill-request promise.
- Rotate the WhatsApp token that appears in plain text in `ANNAM_N8N_WORKFLOWS_CLAUDECODE.md`.
