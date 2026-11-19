#!/bin/sh
set -eu
# Deliberately refuse the production database or a service with outbound providers.
[ "${POSTGRES_DB:-}" = annam_php_preview ] || { echo 'Preview requires its dedicated annam_php_preview database.' >&2; exit 1; }
[ "${PAYMENTS_ENABLED:-0}" = 0 ] && [ "${MESSAGING_ENABLED:-0}" = 0 ] || { echo 'Preview providers must remain disabled.' >&2; exit 1; }
: "${APP_SECRET:?Missing APP_SECRET}"
: "${SEED_OWNER_PASSWORD:?Missing generated owner password}"
export APP_URL="${APP_URL:-https://${RENDER_EXTERNAL_HOSTNAME:?Missing Render hostname}}"
export APP_ENV=preview
export DATABASE_DSN="pgsql:host=${POSTGRES_HOST:?};port=${POSTGRES_PORT:-5432};dbname=${POSTGRES_DB};sslmode=${DATABASE_SSLMODE:-require}"
export DATABASE_USER="${POSTGRES_USER:?}"
export DATABASE_PASSWORD="${POSTGRES_PASSWORD:?}"
export MEDIA_ROOT=/var/annam-data/media
export PUBLIC_MEDIA_ROOT="$MEDIA_ROOT"
export PRIVATE_BILLS_ROOT=/var/annam-data/private-bills
export DJANGO_SETTINGS_MODULE=config.settings.prod
export ALLOWED_HOSTS="${RENDER_EXTERNAL_HOSTNAME:-localhost}"
export SEED_DOMAIN="${RENDER_EXTERNAL_HOSTNAME:-localhost}"
export SEED_ONLY_IF_EMPTY=1 SEED_SYNC_OWNER=0 SEED_DOWNLOAD_ASSETS=0 SEED_RESTORE_MEDIA=0
mkdir -p "$MEDIA_ROOT" "$PRIVATE_BILLS_ROOT" /var/annam-data/sessions /var/annam-data/logs php-app/storage
# Persist only runtime data, never source code or credentials from an image.
ln -sfn /var/annam-data/sessions php-app/storage/sessions
ln -sfn /var/annam-data/logs php-app/storage/logs
/opt/seed-venv/bin/python manage.py migrate --noinput
/opt/seed-venv/bin/python scripts/seed_local.py
php php-app/bin/prepare-copy.php --confirm-test-copy
chown -R www-data:www-data /var/annam-data php-app/storage
# Render supplies PORT; Apache must listen on the same port.
port="${PORT:-10000}"
case "$port" in ''|*[!0-9]*) echo 'Invalid PORT' >&2; exit 1;; esac
printf 'Listen %s\n' "$port" > /etc/apache2/ports.conf
sed -i "s/\*:10000/*:$port/" /etc/apache2/sites-available/000-default.conf
exec apache2-foreground
