# Annam Foods PHP rebuild — first review build

This is a **separate custom PHP application**, not a WordPress plugin. It reuses
the current visual assets and PostgreSQL schema. No Python, Django, Node.js,
Composer, Docker or continuously running worker is needed to serve this PHP
preview. The existing Django application is unchanged and remains the working
reference. This directory is on the `php-rebuild` branch, not deployed to Render.

## What you can review now

- Store admin login using existing active Django PBKDF2-SHA256 passwords and store
  memberships; CSRF, private sessions and a persistent login-attempt throttle.
- Dashboard and separate Meals / Other items management.
- Add/edit/archive dishes, category management, photos saved under media/.
- Breakfast/lunch/dinner menus for a selected date, highlighted Today/Tomorrow,
  an explicitly empty menu, revision checks, and preserved existing stock counters.
- Delivery area names, exact pincodes, per-meal coverage, fees and minimums.
- Meal times, offer banners, website pages and basic store contact/logo settings.
- Public home, daily menu, shop/category search, product pages and cart.
- Server-side prices, stock and cutoffs, separate meal/shop carts, pincode checks,
  area selection and minimum FOOD subtotal before the delivery fee is added.

**This is not yet a replacement for the live website.** Order submission and
checkout payments are visibly disabled. Razorpay callbacks/refunds, billing,
order fulfilment, WhatsApp inbox/sending/sync, n8n callbacks, full courier-settings
editing, saved design/image endpoint compatibility, tax calculations and full
visual parity still need migration and acceptance tests. Production APP_ENV is
refused. Do not enable payments, change DNS or replace the live database.

The original contact/policy content and all actual uploaded photographs must
come from the user's saved database and media backup. A source catalog snapshot
is not proof of current menu dates, prices, delivery settings or customer data.

## Run against a test COPY of the database

1. Install PHP 8.2+ with `pdo_pgsql`, `openssl`, `fileinfo` and sessions. Confirm
   Hostinger allows TLS PostgreSQL connections to your Supabase endpoint. Its
   shared hosting may not provide `pdo_pgsql`; this is a deployment prerequisite.
   `hosting-check.php` can be uploaded temporarily to public_html to report only
   these extension flags, without revealing configuration or credentials. Delete
   it after checking. A PHP plan alone does not prove PostgreSQL compatibility.
2. Restore the current database backup to a separate local/test PostgreSQL
   database or a separate Supabase project. Do not use production credentials.
3. Copy `.env.example` to `.env`, set that test database's connection details,
   a new random APP_SECRET, and the preview URL. Keep this file private.
4. Copy the saved media folder into `public/media/`. Do not commit it.
5. Run:

   ```sh
   php bin/preflight.php
   php bin/prepare-copy.php --confirm-test-copy
   php -S 127.0.0.1:8091 -t public router.php
   ```

6. Visit `http://127.0.0.1:8091/` or `/manage/login/`. Existing active store-member
   accounts can log in. Other Django hash formats require separate compatibility
   work or resetting the password in the test copy; no live passwords are changed.

Every store-owned query is scoped to STORE_SLUG's tenant ID, including joined
rows, item edits and date menus. Unknown hostnames are refused. All mutations use
POST and CSRF. Archive actions preserve historical products instead of deleting
their order relationships. Prices use an exact decimal parser and integer minor
units only inside the PHP monetary layer; no floating-point arithmetic is used.

## Hostinger upload structure

Only `public/` is the web root. Upload its contents to `public_html`, and put the
rest of the application in a private directory outside `public_html`. Update
`public_html/index.php` to require that private `src/bootstrap.php` location.
Do **not** upload `.env`, database dumps, source folders or private logs into
public_html. Apache rewrites are in public/.htaccess. Images live under media/;
block PHP execution there with the supplied media/.htaccess file.

The complete production deployment ZIP and database cutover will be prepared
only after all remaining application features and Hostinger compatibility pass.
Set MEDIA_ROOT to the actual absolute public_html/media directory when the
private application and public root are separated. Keep the media/.htaccess
protection, which blocks executable uploads and legacy draft-library files.

## Checks

`php tests/run.php` runs behavioural checks against an explicitly configured
disposable test database. It rolls back its fixture records. No test calls real
payment providers, sends WhatsApp messages or uses the production database.
