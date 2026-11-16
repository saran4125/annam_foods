# Python UI on the PHP application

The UI reference is Python commit `6b626cb` on `main`. Runtime remains PHP 8.2+
with SQLite; the database, authentication, CSRF, checkout, payments, reports and
messaging services remain PHP. No Django or Python server is required on hosting.

The port uses the same `owner.css` and `storefront.css`, plus the reference
Dashboard, checkout, reports and order-group styles. PHP templates use the
reference components for the sidebar, login, dashboard, dish thumbnails, switches,
meal tabs, date selection, searchable daily-menu editor, photo drop zone, storefront
navigation/search, hero/offer slider, product cards, meal tabs, shop, item and cart.
PHP adapters in `python-ui.css` and `python-ui.js` retain ordinary POST forms and
server-side validation. Existing provider settings, refund, billing, reports and
inbox tools remain accessible; integration credentials are not included.

This is a template port, not a conversion to Django. Exact photographs, stock,
menu availability and counts depend on the store database. The bundle contains
only the reviewed public catalog, approved delivery zones and local media, with
no live customer/order history, existing user accounts or provider credentials.
The ten screenshot-reviewed breakfast products are included; Rava uppuma and
Rasam Vadai are sold out. Rava uppuma has no verified photo. Existing meal dates
are preserved. The latest saved Breakfast, Lunch and Dinner continue on later
unsaved dates; a saved changed or empty meal takes precedence. Daily portion
counters are separate. Staff can disable this under Store settings → Ordering.
Snacks retain their existing date/weekday schedule. Save the reviewed dishes using
Choose dishes to establish the desired starting menu; adding a catalog item alone
does not schedule it.

The homepage defaults to the approved podi photographs (retailer IDs KEI1, MRP1,
PP2 and PT4); existing explicit `theme.hero_product_ids` and website photo choices
take precedence. Product/category photos and counts come from each installation's
own catalog. The header has compact cart/search controls; category shelves have
counts and scrolling arrows; product grids use the reference responsive columns.
Add/plus/minus controls retain server-side validation and ordinary POST fallback.
Checkout uses the reference two-column layout, with a mobile stacked summary.
Asset URLs include content hashes so updated CSS/JS bypass old browser caches.

## Rebuild the complete fresh-install ZIP

```sh
php bin/prepare-local-release.php /PRIVATE/reference.sqlite --reference-catalog-only
php bin/prepare-python-ui-release.php
php bin/package-local.php
```

The final ZIP contains `public_html` and `annam-private`. Keep `annam-private`
outside the public web root. Follow `READ-ME-FIRST.txt`, then use the one-time
code in `annam-private/SETUP-ACCESS.txt` to create your own owner login. Never
upload a fresh seed database over an existing installation. Back up the existing
database, installation configuration and media before any update.

## Verification

PHP syntax checks, the business regression suite, SQLite contract/concurrency and
encrypted recovery tests, extracted-ZIP first-time setup, authenticated management
pages, dated-menu/combined-meal checkout and billing, desktop/mobile screenshots,
private-path denial, and archive SHA-256/entry checksums are run during preparation.
The browser scripts use disposable databases and generated private test accounts.
Real payment, WhatsApp and hosting acceptance remain separate integration checks.

## Update an existing PHP installation

Use the **code-only update ZIP**, not the complete installer. Back up your current
SQLite database, private configuration and uploaded media together first.

For the split hosting layout, merge `annam-private` into the existing private
folder and `public_html/assets` into the public assets folder. For a repository
checkout, copy `annam-private/{src,views,resources,bin,deploy}` to the corresponding
`php-app` folders and `public_html/assets` to `php-app/public/assets`.
The update archive excludes SQLite files, `.env`, storage, keys, setup credentials,
and uploaded media; it does not replace your accounts, orders or catalog.
Restart PHP-FPM / clear hosting OPcache after replacing PHP files, then hard-refresh
the browser. Confirm the offer banner, compact Cart, category arrows/counts,
manage pages and Store settings meal-continuation toggle. No Python service or
Django database migration is needed. A Git push alone does not update a separately
hosted PHP server.
