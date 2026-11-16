# Python UI on the PHP application

The UI reference is Python commit `08b33a1` on `main`. Runtime remains PHP 8.2+
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
are preserved; staff must save actual menus through Choose dishes.

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
