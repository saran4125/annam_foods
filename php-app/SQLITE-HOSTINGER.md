# Annam Foods — local database package

This package runs PHP with a **SQLite file on Hostinger**. It does not connect to
Supabase or another cloud database. It is a custom PHP application, not WordPress.

## Upload and first setup

1. In Hostinger's file manager, open the domain folder that contains `public_html`.
2. Upload/extract the ZIP there. Keep `annam-private` beside `public_html`, outside
   the public website. Merge the package's public_html contents into public_html.
3. Select PHP 8.2+ with PDO SQLite, cURL, mbstring, fileinfo, OpenSSL and ZIP.
   Enable HTTPS. The PHP user must be able to write annam-private/storage and media.
   Do not use world-writable permissions.
4. Visit your HTTPS domain. Open the private `annam-private/SETUP-ACCESS.txt` in
   your file manager, enter its one-time code on the setup page and create your
   own admin username/password. There is no shared default password.
5. Sign in at `/manage/`. Review contact/legal details, delivery rules/prices and
   stock. Save the actual menus for today/tomorrow before accepting meal orders.

No database creation, SQL import, Supabase configuration, Composer or Python is
needed to run the supplied local package. The one-time code is invalidated after
setup; the setup route then redirects to login. Keep your private configuration.

## What is stored where

- `annam-private/storage/annam.sqlite`: products, menus, customer/order/bill data,
  settings, inbox, payment records and background queue.
- `annam-private/storage/installation.json`: unique private configuration and keys.
- `public_html/media/`: local logos and uploaded images.
- `annam-private/storage/sessions/`, `logs/`, `backups/`, `bills/`: private files.

The database is outside public_html. Extra access rules block private sources,
database files, journals and archives if files are accidentally misplaced. Keep
this separation. All orders stay on this hosting account; uploads do not require
an external storage provider.

## Included data and photo limitation

`DATA-INCLUDED.json` records the reviewed local catalog/settings included in this
ZIP. Test customers/orders, old local logins and integration credentials are
excluded. This is **not a fresh export of your live Supabase business history**.
If that history is needed, migrate a backed-up live database copy using the
provided `bin/migrate-sqlite.php` before cutover; never replace live history with
this clean seed.

The original product-photo library is not present in the supplied workspace and
the original image host returns HTTP 403. Available local logos/media are included;
missing product photos display “Photo coming soon”. Restore your saved media
folder and matching image references, or upload photos through admin. No invented
product photos or remote image dependencies have been added.

## Payments, WhatsApp and courier notices

Manual ordering/billing work locally. Razorpay and WhatsApp code is included,
but execution stays offline until you configure accounts and verify real provider
callbacks/templates. Set PAYMENTS_ENABLED/MESSAGING_ENABLED in a private .env only
after staging acceptance. External providers still need internet access even
though the database is local.

For queues/reconciliation, schedule the hosting PHP cron every minute:

    /usr/bin/php /ABSOLUTE/annam-private/bin/cron.php

Cron uses the local database. Enable REQUIRE_CRON=1 only after confirming the
one-minute schedule; `/readyz` then detects an old worker heartbeat.

## SQLite reliability and backups

SQLite runs on the hosting account's local disk. The application enables foreign
keys, WAL journaling, FULL synchronization and a bounded busy timeout. Write
transactions use BEGIN IMMEDIATE; financial/menu/stock changes remain atomic and
nested operations use savepoints. This suits one-store ordering on one hosting
server. Do not put the active file on a network share or share it across multiple
web servers. Hostinger storage must support normal SQLite file locking.

Do not copy only the main `.sqlite` file while the application is running: recent
committed data may be in its WAL file. Use the supplied snapshot/encrypted backup
commands or stop writes before copying the DB with its journals.

Set BACKUP_PASSPHRASE privately to at least 24 random characters, kept separately
from backups. Then run:

    php bin/recovery.php create /PRIVATE/annam-backup.enc
    php bin/recovery.php verify /PRIVATE/annam-backup.enc
    php bin/recovery.php extract /PRIVATE/annam-backup.enc /PRIVATE/new-recovery-folder

The encrypted archive includes a consistent SQLite snapshot, media and private
recovery keys/settings. To restore, stop writes, verify/extract into a private
folder, then use:

    php bin/recovery.php restore-sqlite /PRIVATE/new-recovery-folder/database.sqlite /PRIVATE/restored-annam.sqlite --confirm-new-file

The command verifies database integrity and refuses to overwrite existing files.
Restore corresponding media and private configuration, test the restored copy,
then switch the configured database path with writes paused. Never serve backup
archives or extracted recovery keys publicly. Back up regularly off the hosting
account too; optional offsite storage is not a runtime database dependency.

## Migrating existing PostgreSQL history

Use a backed-up source database COPY and configure its private DATABASE_DSN,
DATABASE_USER and DATABASE_PASSWORD in the migration environment. Run:

    php bin/migrate-sqlite.php /PRIVATE/new-annam.sqlite --confirm-copy

This copies IDs, relationships, decimal strings, dates, encrypted provider records
and business history into SQLite. It does not modify the source. Preserve the
original SECRETS_KEY for imported encrypted credentials and the original media.
Rehearse migration and compare record counts and sample bills before switching.
Changing databases does not automatically move original media files. If the
local setup screen appears for an imported full database, use its private setup
code with the existing owner username/password (and repeat that password in the
confirmation field). Setup validates the existing owner instead of replacing
accounts or resetting their passwords.

## Updating this installation

Back up first. Replace application source/assets only. **Do not overwrite** your
existing storage/annam.sqlite, installation.json, media, sessions or backups with
files from a fresh ZIP. Keep the previous application version for rollback.
