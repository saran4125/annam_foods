#!/bin/sh
set -eu
# This preview never connects to an external or production database.
[ "${PAYMENTS_ENABLED:-0}" = 0 ] && [ "${MESSAGING_ENABLED:-0}" = 0 ] || { echo 'Preview providers must remain disabled.' >&2; exit 1; }
: "${APP_SECRET:?Missing APP_SECRET}"
: "${SEED_OWNER_PASSWORD:?Missing generated owner password}"
export APP_URL="${APP_URL:-https://${RENDER_EXTERNAL_HOSTNAME:?Missing Render hostname}}"
export APP_ENV=preview
export PREVIEW_DATA_ROOT="${PREVIEW_DATA_ROOT:-/tmp/annam-php-preview}"
case "$PREVIEW_DATA_ROOT" in
 /tmp/annam-php-preview) echo 'Temporary preview storage: container replacement resets data.' ;;
 /var/data/annam-php-preview) /opt/seed-venv/bin/python -c 'import os; mounted=os.path.ismount("/var/data") or any(len(line.split())>4 and line.split()[4]=="/var/data" for line in open("/proc/self/mountinfo")); assert mounted, "Persistent /var/data must be mounted; refusing temporary fallback"' ;;
 *) echo 'Unsupported preview data directory.' >&2; exit 1 ;;
esac
export DATABASE_DSN="sqlite:$PREVIEW_DATA_ROOT/annam.sqlite"
export DATABASE_USER= DATABASE_PASSWORD=
export MEDIA_ROOT=$PREVIEW_DATA_ROOT/media
export PUBLIC_MEDIA_ROOT="$MEDIA_ROOT"
export PRIVATE_BILLS_ROOT=$PREVIEW_DATA_ROOT/private-bills
export SEED_DOMAIN="${RENDER_EXTERNAL_HOSTNAME:-localhost}"
export SEED_ONLY_IF_EMPTY=1 SEED_SYNC_OWNER=0 SEED_DOWNLOAD_ASSETS=0 SEED_RESTORE_MEDIA=0
mkdir -p "$MEDIA_ROOT" "$PRIVATE_BILLS_ROOT" "$PREVIEW_DATA_ROOT/sessions" "$PREVIEW_DATA_ROOT/logs" php-app/storage
ln -sfn "$PREVIEW_DATA_ROOT/sessions" php-app/storage/sessions
ln -sfn "$PREVIEW_DATA_ROOT/logs" php-app/storage/logs
/opt/seed-venv/bin/python php-app/deploy/render-init.py
# SQLite's schema is already present; restore only the bundled public media.
php php-app/deploy/render-catalog.php
php php-app/deploy/render-media.php
chown -R www-data:www-data "$PREVIEW_DATA_ROOT" php-app/storage
# Render supplies PORT; Apache must listen on the same port.
port="${PORT:-10000}"
case "$port" in ''|*[!0-9]*) echo 'Invalid PORT' >&2; exit 1;; esac
printf 'Listen %s\n' "$port" > /etc/apache2/ports.conf
sed -i "s/\*:10000/*:$port/" /etc/apache2/sites-available/000-default.conf
exec apache2-foreground
