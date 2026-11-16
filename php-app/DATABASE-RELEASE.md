# Reviewed PHP database release

This is a **fresh-install public catalog database**, not a live Render database
export and not a replacement for an installation containing accounts or orders.

It combines the checksum-verified original PHP public SQLite snapshot with the
reviewed Python manifests at `6b626cb`. It contains 325 products, 64 approved
Chennai delivery areas with their charges/minimums/meal restrictions, plain meal
categories, four meal slots, pages, banners and the ten reviewed breakfast dishes
scheduled from 16 November 2026. Eight breakfast products are in stock; the
reviewed Rava uppuma and Rasam Vadai stock flags are preserved as sold out.
Breakfast, Lunch and Dinner continue from the latest saved menu until changed.
Historical source menus remain intact. No demo Coimbatore zones/non-vegetarian
products, customer history, order history, login accounts or provider credentials
are included.

Public comparison on 16 November verified the names, prices and photo contents
of 10 breakfast, 7 lunch and 6 dinner dishes published by the new Python site.
Equivalent photograph files can have different catalog/menu paths. Public pages
do not establish hidden product state, stock flags, complete dated-menu contents,
private settings or transaction history. The original snapshot also retains a
Chapathi (1) dinner row absent from the published Python menu; it has not been
silently deleted. Full reconciliation requires a current live database export.
Both supplied Render endpoints closed PostgreSQL connections before
authentication during preparation. No live PostgreSQL rows were changed.

## Fresh installation only

1. Download the updated PHP source and reviewed database ZIPs from GitHub.
2. Use a new installation folder. Keep `annam-private` outside `public_html`.
   Put the source's PHP `src`, `views`, `resources`, `bin`, and `deploy` directories
   in `annam-private`; public PHP entry/assets stay in `public_html`.
3. Copy `database/annam.sqlite` from the database ZIP to
   `annam-private/storage/annam.sqlite`. The archive deliberately stores it under
   `database/` so extracting cannot overwrite an active database automatically.
4. Keep the original image files in `public_html/media`; this small database ZIP
   contains no photographs. The repository's `media` directory contains recovered
   public images. Enable PHP 8.2+ and the extensions listed in SQLITE-HOSTINGER.md.
5. From `annam-private`, run `php bin/init-local.php --new-store`. It creates
   private keys and a one-time setup file locally; no credentials are in GitHub.
6. Read private `SETUP-ACCESS.txt`, open your HTTPS domain `/setup/`, and create
   your owner login. Review menus, stock and business settings before taking orders.

For a source-checkout deployment, put the database in `php-app/storage` and run
`php bin/init-local.php --new-store` inside `php-app`; configure an absolute
`MEDIA_ROOT` and the public web root as described in README.md.

**Existing installations:** retain the current SQLite database and configuration.
This fresh seed contains no existing accounts/orders and must not replace those
records. Obtain a consistent backup/export for a merge that preserves their IDs
and financial snapshots. Raw PostgreSQL URLs are stored privately, never in Git.
