# Phase 6 — Super admin and subscription billing

> **Superseded by [PLAN.md](PLAN.md) v2 (28 September 2026).** Kept as implementation detail; the platform is specified in PLAN.md §12 and built in Phase G (§17). Where this file and PLAN.md differ, PLAN.md wins.

## Goal

Provision a kitchen in under an hour, collect ₹5,000/month without chasing
anyone, and shut off a client who stops paying — without destroying their data
or blindsiding their customers.

Needed before client #2. Not before client #1.

---

## Super admin

Django admin does most of this. Gate it to `platform_admins` on
`settings.PLATFORM_HOST` (`admin.localhost` in dev), which the tenant
middleware already leaves without a tenant. That is deliberate: platform code
must call `all_tenants()` explicitly rather than inherit a tenant by accident.

Already built in Phase 1: `TenantAdmin` with status actions,
`TenantConfigInline`, `TenantDomainInline`, `UnscopedAdmin`.

Still to add:

- **Provisioning form** — a single screen wrapping `provision_tenant`: name,
  slug, domain, owner email, menu mode, timezone. Creates tenant, config,
  domain, owner user and emails credentials.
- **Impersonation** — view a tenant's backend as its owner for support.
  Every impersonated request writes an `AdminAuditLog` row. Never allow
  impersonation to place an order or change payment settings.
- **Health view** — one row per tenant: orders in the last 7 days, last order
  at, WhatsApp configured, Razorpay configured, subscription state. This is how
  you notice a broken client before they phone you.
- **`AdminAuditLog`** — `actor`, `tenant`, `action`, `detail`, `at`. Every
  status change, impersonation and secret update.

---

## Models — `apps/billing/`

Not `TenantOwnedModel`. These belong to SEER and are read with `all_tenants()`.

### `Subscription`
```
tenant                OneToOne Tenant
amount                Decimal   default 5000
cycle                 CharField  monthly
status                CharField  trialing active past_due cancelled
current_period_start  DateField
current_period_end    DateField
grace_until           DateField, null      # manual override
mandate_id            CharField(80), blank # Razorpay subscription / UPI autopay
created_at            DateTimeField
```

### `SubscriptionInvoice`
```
tenant        FK Tenant
number        CharField(30), unique
amount        Decimal
due_date      DateField
paid_at       DateTimeField, null
payment_link  URLField, blank
status        CharField  open paid overdue void
```

### `TenantSecrets` — already built

Lives in `apps.tenancy`, encrypted with Fernet using `settings.SECRETS_KEY`.
Secrets are read and written through properties, so callers never touch
ciphertext and never forget to encrypt. `TenantSecretsForm` gives the
write-only portal pattern: a masked display of what is stored, a blank input
that keeps it, a filled input that replaces it, and no reveal toggle.

What Phase 6 adds: surfacing it in the owner's own backend (Phase 4 covers the
UI), key rotation tooling, and `SECRETS_KEY` required from the environment in
production settings.

---

## The suspension ladder

A single on/off switch is the wrong shape. Kill a live kitchen's site at 8pm on
a Saturday and you don't collect ₹5,000 — you create an emergency and a story
that travels through a small industry. Squeeze the owner before his customers.

`TenantStatus` already encodes this, and `Tenant.can_take_orders` /
`backend_is_read_only` / `shows_billing_banner` already implement the effects.
Phase 6 adds the automation that moves a tenant between rungs.

| Rung | When | Effect |
|---|---|---|
| `active` | paid | everything works; reminder at T−7 days |
| `past_due` | day 1–6 | owner sees a banner with a pay link; WhatsApp reminders. **Storefront and bot untouched** — customers notice nothing |
| `restricted` | day 7–13 | backend read-only except billing. Storefront still sells. He feels it every morning; his revenue doesn't stop |
| `suspended` | day 14+ | ordering off. Storefront shows the menu and a neutral notice; bot gives the kitchen's own phone number. Owner keeps full login, can read and export everything. **No data touched** |
| `cancelled` | manual only | never automatic. Domain released, full export handed over, records kept 90 days |

### Two safeguards, build them on day one

- **Transitions fire at 04:00 in the tenant's local timezone**, from the
  scheduled job — never mid-service.
- **A one-click "grant grace" action** setting `grace_until`, which the job
  respects. The client who is late is usually having a bad month, not cheating
  you.

### The job — `billing_ladder`, daily

```
with all_tenants():
  for each Subscription:
     skip if grace_until >= today
     days_overdue = today - current_period_end
     move to the rung for that many days, only ever one step at a time
     write an AdminAuditLog row and notify the owner on each transition
```

Never skip rungs. A tenant going straight from `active` to `suspended` because
a job didn't run for a week is exactly the emergency this design avoids.

## Collecting the money

**The kill switch is a backstop, not a collection method.** Set up **Razorpay
Subscriptions with a UPI autopay mandate at onboarding** so ₹5,000 debits
itself. Chasing ten clients by hand every month is a part-time job you'd be
doing for free.

- `create_subscription_mandate(tenant)` — during provisioning
- webhook for subscription charges: mark `SubscriptionInvoice` paid, roll the
  period forward, return the tenant to `active`
- fall back to a payment link emailed and WhatsApped when no mandate exists

---

## Behaviours that must be tested

- each rung produces exactly the documented effects on storefront and backend
  (some of this is already covered in `apps/storefront/tests/test_storefront.py`)
- the ladder advances one rung at a time, never skipping
- `grace_until` in the future freezes the ladder entirely
- paying returns the tenant to `active` from any rung
- a suspended tenant's owner can still log in, list orders and export
- **no rung ever deletes data**
- transitions fire at 04:00 local, not UTC — a tenant in a different timezone
  is not suspended mid-service
- secrets: a saved Razorpay secret never appears in any HTTP response body
- impersonation writes an audit row and cannot place an order

---

## Also in this phase, if there is room

- Coupons and cashback (`offers` model from the blueprint)
- GST fields rendered on the invoice PDF
- Tamil copy behind a `TenantConfig.features` flag
- The client-facing onboarding guide — written once, so you are not explaining
  WABA setup ten times. This is the highest-leverage document in the business.

---

## Out of scope

Self-serve signup; a public pricing page; reseller accounts; anything that
assumes more than ~20 tenants.
