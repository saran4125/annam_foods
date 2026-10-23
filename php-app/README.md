# Annam Foods — PHP application

A custom PHP storefront and administration application using the existing
PostgreSQL/Supabase schema. It is **not a WordPress plugin**. Python, Django,
Composer and a continuous worker process are not required to serve it. Keep
Django available as the rollback/reference application until staging acceptance.

The PHP migration is on `php-rebuild`. It has not replaced the live Render site.
Live provider verification and Hostinger deployment are separate from local tests.

## Application features

- Existing store accounts and PBKDF2-SHA256 passwords, scoped permissions, private
  sessions, CSRF and persistent login throttling; direct Annam admin login.
- Products, categories, images, offers, pages, meal times and delivery areas.
- Dated breakfast/lunch/dinner menus, Today/Tomorrow selection, revision conflicts,
  weekly fallback and explicitly empty saved menus without deleting products.
- Published section order/content/colours/photos, contact/footer information and
  legacy image URLs; recovery of database-backed photos into media files.
- Separate meal and shop carts; server prices, stock/cutoff/holiday checks, exact
  approved pincodes, area-specific food minimums and delivery charges.
- Checkout details, explicit total review, idempotent submission, browser-private
  receipts and bills; manual, COD and enabled Razorpay payment choices.
- Staff/WhatsApp bookings, fulfilment history and transitions, manual payment
  confirmation, immutable bills, locked financial-year numbering and credit notes.
- Fixed-point tax/rounding calculations and saved order/invoice snapshots. The
  compact logo receipt includes customer delivery details and Print / Save PDF.
- Razorpay test/live connections, encrypted write-only credentials, provider
  order creation, uncertain-request reconciliation, capture/signature validation,
  signed/deduplicated callbacks, retries, verified refunds and credit notes.
- WhatsApp inbox, queued replies, provider status receipts, Meta/n8n sync,
  signature/token authentication, account filtering, private attachments,
  forwarding queue and scheduled delivery/reconciliation.
- Read-only migration fingerprints, media inventory/ZIP backup, preflight and
  separate Hostinger package. No SEER, domain-management or Appearance UI.

A test Razorpay capture never issues a real bill. Manual payment confirmation
requires an explicit staff acknowledgement. Mirrored WhatsApp messages do not
silently become billable orders; staff create the booking from a conversation.
PDF export uses the browser's Print / Save PDF, matching the existing application.
No public customer invoice archive or automatic PDF WhatsApp broadcast is added.

## Requirements

PHP **8.2+**, `pdo_pgsql`, `curl`, `openssl`, `mbstring`, `fileinfo`, `zip`, sessions
and zlib. Apache/LiteSpeed rewrites, persistent writable media/private storage,
outbound HTTPS to providers and TLS PostgreSQL access to Supabase are required.
Schedule a PHP CLI cron every minute. A PHP or WordPress hosting plan alone does
not establish PostgreSQL support: verify these capabilities on your Hostinger
account before cutover. `hosting-check.php` is an optional temporary extension
check without phpinfo or credentials; remove it after use.

## Stage a database copy first

1. Restore the current PostgreSQL backup into a **separate database/project**.
   Do not use production credentials for development. Preserve the existing
   schema, IDs, relationships and all financial/message history.
2. Copy `.env.example` to private `.env`; configure the clone connection and URL.
   Generate a new random APP_SECRET of at least 32 characters for PHP sessions.
   Preserve the **original Render SECRETS_KEY** to decrypt saved integration
   secrets. Original Django SECRET_KEY is optional as DJANGO_SECRET_KEY to keep
   old guest receipt links accessible in their originating browsers. Never send
   or commit either secret. Staff sign in again; staff sessions are not migrated.
3. Copy the complete saved media folder to `public/media` or the absolute
   MEDIA_ROOT. Leave the supplied media `.htaccess` protection in place.
4. Run:

   ```sh
   php bin/preflight.php
   php bin/prepare-copy.php --confirm-test-copy
   php bin/audit.php --readiness
   php bin/audit.php --baseline=/private/path/annam-before.json
   php -S 127.0.0.1:8091 -t public router.php
   ```

Preparation adds only the PHP login-throttle table/index and missing bundled or
recoverable photo files. It does not seed/overwrite products, menus, zones,
settings, customers, orders, invoice sequences or integration credentials.
Readiness fails if known photo references are missing or external, legal/delivery
settings are invalid, encrypted credentials cannot be read, or bill totals differ
from orders. An empty test catalog/photo inventory is not proof that the real
media backup is complete.

The fingerprint command hashes every scoped table without printing customer
information or secret values. With writes paused, compare immediately after an
import/preparation:

```sh
php bin/audit.php --compare=/private/path/annam-before.json
```

Differences after actual test orders/menu edits are expected; compare the untouched
restored copy first. A baseline is an integrity report, **not a database backup**.
Keep database and media backups outside public_html and rehearse restoring both.

## Hostinger package and upload

```sh
php bin/package-hostinger.php
```

This creates `dist/annam-foods-hostinger.zip`:

```
annam-private/              outside the public web root
  .env.example             copy to .env and configure privately
  src/ views/ resources/ bin/ storage/
public_html/
  index.php                loads ../annam-private/src/bootstrap.php
  .htaccess
  assets/
  media/.htaccess           merge your complete saved media here
CHECKSUMS.json
INSTALL-FIRST.txt
```

Extract at the domain directory containing public_html, so annam-private is its
sibling. If your file manager extracts inside public_html, **move annam-private
outside it** and adjust the front controller path. Source files, private .env,
logs, sessions and backup archives must not be web-accessible. Set MEDIA_ROOT to
the absolute `public_html/media` directory. Keep private .env owner-readable only;
make private sessions/logs/storage and public media writable by PHP. Do not use
world-writable permissions.

Set APP_URL to the final HTTPS address and APP_ENV=production only after staging
checks pass. The app accepts that hostname only; configure HTTPS and any preferred
www/non-www redirect in hosting. No domain-management admin screen is required.
If CLI execution is restricted, use Hostinger's PHP cron facility; a production
site needs scheduled processing for the queue and reconciliation.

Example cron (replace the PHP binary and absolute account path):

```cron
* * * * * /usr/bin/php /home/ACCOUNT/domains/DOMAIN/annam-private/bin/cron.php >> /home/ACCOUNT/domains/DOMAIN/annam-private/storage/logs/cron.log 2>&1
```

The worker takes bounded, locked batches, uses retry limits/backoff and recovers
expired claims. n8n should deduplicate using the supplied message_id. As with the
original worker, an HTTP timeout after a provider accepted a send can leave
uncertain delivery; verify the provider timeline before manually resending.

## Provider acceptance and cutover

Before replacing Django, test these on a private staging clone:

1. Meals: valid/invalid pincode, shared-pincode area choice, food minimum excluding
   delivery fee, cutoffs/holidays, dated menu, duplicate checkout and mobile flow.
2. Shop: courier disabled, approved/unlisted pincode, minimum and fee; no mixed cart.
3. Razorpay sandbox: successful capture, failed/cancelled payment, lost browser
   callback, duplicate signed webhook, retry/reconciliation and full refund.
   Test captures are visibly test payments and do not create legal bills.
4. Bills: real seller/FSSAI/tax settings, original logo, customer delivery address,
   exact totals, duplicate issuance, unchanged historic bills and one-page lunch
   export. Do not record a real payment merely to create an example.
5. WhatsApp: incoming text/media, outgoing reply, delivered/read receipts, sync
   bearer token, duplicate events, 24-hour window, Meta-to-n8n forwarding and cron.
   Keep existing n8n logic; point its inbox/status-copy nodes at the PHP endpoints.
6. Restore a backup, compare fingerprints, verify all media, staff permissions,
   policy/contact content and HTTPS. Confirm Hostinger outbound DB/provider access.

Callbacks retain existing paths:

- `/platform/webhooks/annam/razorpay/test/` and `/live/`
- `/webhooks/whatsapp/`, `/webhooks/whatsapp/n8n/`
- `/platform/webhooks/annam/whatsapp/` and `/whatsapp/n8n/`
- `/platform/assets/annam/<uuid>/` (only published references are public)

For cutover, stop accepting new Django orders and pause its worker; take fresh DB
and media backups, record a fingerprint, restore/import if changing databases,
run `prepare-copy.php --confirm-migration`, verify fingerprints/readiness, update
provider callbacks and cron, then switch hosting/DNS. Run only one sending worker
and one active website at the cutover. Keep a documented rollback point; if PHP
has already accepted orders, preserve those writes before restoring anything.

## Verification

```sh
php tests/run.php
php bin/preflight.php
```

Native tests require a disposable DB named with `preview` or `test`; fixtures are
rolled back, including financial rows. They use fake provider responses and do
not send messages or collect/refund real money. `tests/browser_check.py` uses
Playwright against a local isolated server, with PHP_TEST_USERNAME and
PHP_TEST_PASSWORD supplied privately. Browser tests deliberately save menus and
create/confirm local test orders; never point them at production.

The original Django PostgreSQL suite remains required before repository commits.
Parsedown 1.8.0 is bundled with its MIT licence for safe Markdown policy pages;
there is no Composer install step on the hosting server.
