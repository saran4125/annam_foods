#!/bin/sh
set -eu
# This preview never connects to an external or production database.
[ "${PAYMENTS_ENABLED:-0}" = 0 ] && [ "${MESSAGING_ENABLED:-0}" = 0 ] || { echo 'Preview providers must remain disabled.' >&2; exit 1; }
: "${APP_SECRET:?Missing APP_SECRET}"
: "${SEED_OWNER_PASSWORD:?Missing generated owner password}"
export APP_URL="${APP_URL:-https://${RENDER_EXTERNAL_HOSTNAME:?Missing Render hostname}}"
export APP_ENV=preview
export DATABASE_DSN=sqlite:/tmp/annam-php-preview/annam.sqlite
export DATABASE_USER= DATABASE_PASSWORD=
export MEDIA_ROOT=/tmp/annam-php-preview/media
export PUBLIC_MEDIA_ROOT="$MEDIA_ROOT"
export PRIVATE_BILLS_ROOT=/tmp/annam-php-preview/private-bills
export SEED_DOMAIN="${RENDER_EXTERNAL_HOSTNAME:-localhost}"
export SEED_ONLY_IF_EMPTY=1 SEED_SYNC_OWNER=0 SEED_DOWNLOAD_ASSETS=0 SEED_RESTORE_MEDIA=0
mkdir -p "$MEDIA_ROOT" "$PRIVATE_BILLS_ROOT" /tmp/annam-php-preview/sessions /tmp/annam-php-preview/logs php-app/storage
ln -sfn /tmp/annam-php-preview/sessions php-app/storage/sessions
ln -sfn /tmp/annam-php-preview/logs php-app/storage/logs
/opt/seed-venv/bin/python php-app/deploy/render-init.py
# SQLite's schema is already present; restore only the bundled public media.
php -r 'require "php-app/src/bootstrap.php"; $store=new Annam\Store(new Annam\Database()); Annam\Media::restore($store);'
chown -R www-data:www-data /tmp/annam-php-preview php-app/storage
# Render supplies PORT; Apache must listen on the same port.
port="${PORT:-10000}"
case "$port" in ''|*[!0-9]*) echo 'Invalid PORT' >&2; exit 1;; esac
printf 'Listen %s\n' "$port" > /etc/apache2/ports.conf
sed -i "s/\*:10000/*:$port/" /etc/apache2/sites-available/000-default.conf
exec apache2-foreground
