# Annam Foods PHP architecture

The `php-rebuild` branch adds the PHP application in `php-app/`. The original
Django tree is retained as the migration reference and rollback implementation.
The PHP runtime does not import or invoke Python. It connects directly to the
existing business schema. The production local package stores it in SQLite on
the hosting account; PostgreSQL is retained as a migration/reference driver.
WordPress is not part of the application.

## Request and data flow

```text
Browser / signed provider callback
    → Apache/LiteSpeed public_html/index.php
    → private src/bootstrap.php (environment, autoload, safe output)
    → Application (host, store, session, CSRF, authentication)
    → Workflow / ParityRoutes / Resources (HTTP adapters)
    → Store-scoped domain services
    → Database / existing PostgreSQL tables

Queued messages / pending payments
    → Hostinger cron: bin/cron.php
    → Worker → Sender / Payments → HTTPS provider APIs
```

Only `public/` (or packaged `public_html/`) is public. Environment configuration,
source, sessions, logs and backups belong outside it. The configured host and
STORE_SLUG resolve one store. Store-owned SQL always includes its tenant ID,
including joined tables and foreign-key choices. Existing tenant columns remain
for data protection; there is no multi-kitchen UI or subscription workflow.

## Modules

| Module | Responsibility |
| --- | --- |
| `Application`, `Workflow` | Routing, authentication gates, CSRF and service/view adaptation |
| `Security` | Private PHP sessions, existing password compatibility, membership, login throttle |
| `Database`, `Store` | Parameterized PostgreSQL access, nested savepoints, scoped records and immutable writes |
| `Resources` | Catalog/content/delivery forms, validated uploads and archive actions |
| `Cart`, `Checkout` | Live prices/availability, delivery checks, review fingerprint and retry-safe placement |
| `Money`, `Pricing` | Exact fixed-point arithmetic, tax inclusion/exclusion and half-up rounding |
| `Orders` | Customer/order snapshots, manual bookings, payment acknowledgement, status flow/events |
| `Payments`, `Razorpay`, `Http` | Frozen payment intents, provider evidence, callbacks, reconciliation and refunds |
| `Billing` | Immutable legal/price/address snapshots, transactional numbering, credits and words |
| `Messaging`, `MessagePayload` | Inbox mirroring, deduplication, payload limits and durable outgoing queue |
| `Worker`, `Sender` | Locked claims, bounded dispatch, retry/backoff, provider transport and forwarding |
| `Crypto`, `LegacySession` | Fernet credentials and read-only compatibility for old guest receipt sessions |
| `Content`, `Markdown` | Published site configuration, escaped copy and safe formatted policy pages |
| `Media`, `Attachment`, `Backup` | Photo recovery/access, authenticated Meta media and scoped ZIP inventory |
| `Delivery`, `StaffBooking`, `CustomerLookup` | Meal/category coverage, shared-area fee, combinations and editable saved addresses |
| `Reports` | SQL product quantities, meal groups and daily financial monitoring |
| `Courier`, `CourierPayments` | Deferred charge ledger, separate provider evidence and customer/team notices |
| `Schema`, `CatalogSync`, `Operations`, `Recovery` | Additive upgrades, reviewed imports, shared throttle, encrypted recovery |
| `Audit` | Read-only migration fingerprints and configuration/data readiness checks |

## Checkout and money

A cart stores item IDs, quantities, meal/date and fulfilment only. Every quote
reads the catalog and resolved menu again. Meal orders require an exact active
pincode/area with applicable meal coverage, minimum food subtotal and fee. Shop
orders use the selected approved Chennai area when applicable. Snacks outside
Chennai use explicitly enabled courier delivery with a deferred-charge disclosure,
including other states/countries. Unapproved Chennai addresses cannot bypass local
coverage. Breakfast/Lunch/Snacks can share one dated order and one fee; Dinner
always requires a separate order. A shop-started cart accepts Snacks only.

Checkout review stores a server-side fingerprint of the quote and contact
information. Submission locks the store and selected items, recalculates the
quote and refuses changed totals/settings. The external reference includes a
random browser key and review reference. Retried submissions return the same
order even after its cart is cleared. A receipt requires that originating browser
key; the UUID alone grants no access.

Orders snapshot line names, unit prices, amounts, taxes, delivery address and
pricing choices. Later product/configuration edits do not rewrite those values.
Financial values are decimal strings at database boundaries, with arithmetic
centralized through Money/Pricing. No floating-point currency calculations.
Existing counters are preserved. Successful web order creation increments resolved
menu quantities under the store lock; abandoned carts do not reserve portions.
Scheduled rows and live prices are checked again before placement.

## Payments and bills

Payment intents freeze mode, key ID, amount and currency. Provider order receipts
retain the legacy `sk_<uuidhex>` form for existing references. After an uncertain
create request, reconciliation searches the existing receipt; it does not blindly
create another provider order. Browser HMAC verification is followed by fetching
authoritative payment evidence. Signed webhooks are deduplicated, and amount,
currency, order ID and captured status must match. Failures cannot downgrade an
already captured/refunded payment.

Razorpay test payments remain visibly test and never issue real bills. Verified
live payments remain recorded when legal billing settings are incomplete; the
billing problem is shown for staff to resolve. Refund confirmation uses processed
provider refund records. Full refunds link a credit note once. Payment credentials
referenced by history are retained for verification/refunds.

Bill creation locks the order/store and invoice sequence inside a transaction.
One primary invoice is allowed per order. Seller, buyer/delivery, item/tax and
payment details are immutable. Totals must equal the paid order before a number
is consumed. Credit notes use their own series and cannot cumulatively exceed
the original bill. The shared compact receipt CSS supports screen and browser
Print / Save PDF with the original logo, nine-item lunch and customer address.

## WhatsApp and background processing

Incoming Meta requests require the configured app-secret signature and account
identifiers. n8n copy events require a separate sync bearer token. Provider message
IDs prevent duplicate timeline entries. Delivery/read receipts are stored even
when they arrive before the outgoing send response. Receipt precedence prevents
a late sent/failed event from replacing a read confirmation. An early n8n mirror
is merged with the app-owned queued reply.

Replies are queued, not sent by controllers. Free-text replies require the
24-hour inbound window. Outside it, use an approved template through automation.
The sender supports Meta Cloud, n8n and local console testing; production rejects
console delivery. n8n receives both the internal payload and Graph payload plus
the outbound message ID for deduplication. Mirroring a conversation does not create
an order: staff explicitly open Create booking.

Cron claims due rows under PostgreSQL locks, releases locks before transmission,
stores results and retries with bounded backoff. Expired sending claims recover.
Meta-to-n8n forwarding is another durable queue. No browser-accessible cron or
secret query parameter is used. Provider attachments require staff access and a
scoped message; downloads use approved Meta hosts, limits and safe content headers.

## Media and deployment

Uploaded catalog images are validated JPG/PNG/WebP files under MEDIA_ROOT with
random names. Bundled recovery images are copied there by preparation. Legacy
editor image data can restore `media/website/<tenant>/<uuid>.<ext>` files. Direct
access to that subtree is denied; the compatible asset endpoint publishes only
current published references and requires staff access for draft/library photos.
Existing bill logo aliases remain usable without editing issued snapshots.

The Hostinger ZIP splits private source and public assets, excludes all secrets,
uploads, sessions/logs and database contents, and includes checksums. The real
saved media and a restored database must be supplied separately. Audit reports
hash scoped records without disclosing personal data or credential values.
Preparation preserves business/history snapshots and adds missing compatibility
fields/tables/indexes and recoverable media. Reviewed catalog/zone imports are
explicit, versioned and separately applied.

Hostinger `pdo_pgsql`, outbound Supabase TLS and provider access, persistent files,
cron, DNS/HTTPS, backup restoration and real provider acceptance require checking
on the actual hosting account. Local mock/browser tests do not certify them. The
cutover/rollback procedure and commands are in README.md.

## Operational parity

Provider execution defaults offline. Enabling payment choices/cron requires the
private runtime flags; courier WhatsApp drafts remain `held` until approved
templates are configured and released. Test courier captures never settle real
receivables. Food totals/bills remain unchanged when separate courier receipts
are recorded. Shared database rate buckets protect login and customer lookup.

Orders use SQL filtering and 50-row pages; report quantities aggregate JSON line
snapshots in SQL. Catalog rendering uses bounded pages, and menu updates use
revision checks with preserved counters. Database statements/locks have bounded
timeouts. `/readyz` combines database/media availability and optional cron freshness.
No particular traffic capacity is certified by these safeguards.

Recovery streams public PostgreSQL data without requiring pg_dump/Python, archives
media/private recovery keys, and encrypts indexed chunks with authenticated final
completion. Verification precedes optional private Supabase Storage upload. Clean
schema/data restoration is transactional and refuses existing business data.
Use the matching release/schema and rehearse recovery before production cutover.

## Local-file database release

Database selects SQLite for the local package. SqliteDialect contains the audited
query translation boundary: PostgreSQL row-lock clauses become whole-writer
transactions, search/JSON/report syntax is adapted, timestamps are canonical UTC
and decimal fields retain TEXT affinity. Money aggregates use integer paise rather
than floating-point SUM. WAL, FULL synchronization, foreign keys and a busy timeout
are enabled per connection. Nested writes use savepoints; external provider calls
remain outside critical writer claims.

SqliteMigration copies a consistent read-only PostgreSQL snapshot into the local
schema, retaining IDs, encrypted data, decimal strings, binary images and history.
It checks foreign keys/integrity and never changes the source. LocalRecovery uses
SQLite VACUUM INTO for a consistent snapshot including committed WAL data, then
authenticated encrypted archiving; restore validates integrity and refuses an
existing destination. Normal uploads must never replace the live DB/config/media.

Installation reads private local configuration and supplies local database/media
paths without manual cloud setup. A single-use private activation code protects
first-owner creation, CSRF and rate limits protect setup requests, and a filesystem
lock serializes configuration activation. Setup is disabled after activation.
The local release is a single-host application; multiple independent web servers
must not share this SQLite file over a network filesystem.
