# Add missing public records from the PHP SQLite snapshot

The checksum-verified protected PHP delivery package at commit `8dce30f`
contains `Annam-Foods/UPLOAD/annam-private/storage/annam.sqlite`. The database
passed SQLite integrity checking. `deploy/annam_php_public_snapshot.json` contains
only its catalog, menu, banner, page and delivery-zone rows. It contains no
credentials, user accounts, customers, orders, financial records or sessions.
All 354 image paths referenced by these rows already exist in the bundled media.

From the Python checkout, with the intended PostgreSQL configuration active:

```bash
python manage.py restore_missing_php_data
python manage.py restore_missing_php_data --apply
```

The default command previews inside a transaction and rolls back. `--apply`
inserts missing records in one transaction. It matches products by retailer ID,
categories/pages by slug, slots by key, zones by pincode and area, banners by
title, and menu records by their item/slot/date or weekday. Source primary keys
are remapped; existing prices, stock, images, fields and foreign keys are never
updated. Ambiguous matches or unresolved references abort the transaction.
Staff-saved date menus, including empty menus, retain their existing contents.
Existing settings, legal/billing details and account/domain configuration stay
unchanged. Historical menu dates stay historical; this does not publish today's
meal menu or guarantee the hero selects the same photos as a previous deployment.

For Render without shell access, deploy this code on `main`, then temporarily set
`RESTORE_MISSING_PHP_DATA=1` in the **annam-foods** service Environment and save
with deployment. The startup background seed/catalog task runs the restore after
provisioning and prints the report. A Live web status alone does not establish
background restore completion: check logs for `"applied": true` and no restore
errors. Remove the flag after successful completion so future staff deletions
are not reversed on restart. No password or raw SQLite database is committed.

Local validation uses a separate development database. The current Render database
must be compared by running the preview there; local missing counts do not describe
Render's contents. Back up the target database before applying.
