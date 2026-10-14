#!/usr/bin/env bash
# Render start: migrate, load Annam on the very first boot only, then serve.
set -euo pipefail

python manage.py migrate --noinput

# First boot: create the kitchen, its owner login, and download the catalog photos
# onto the persistent disk. SEED_ONLY_IF_EMPTY makes every later restart a no-op,
# so owner edits are never overwritten. Runs in the background so the site is
# already answering health checks while photos download.
export SEED_DOMAIN="${SEED_DOMAIN:-${RENDER_EXTERNAL_HOSTNAME:-}}"
if [ -n "${SEED_OWNER_PASSWORD:-}" ] && [ -n "${SEED_DOMAIN}" ]; then
  SEED_ONLY_IF_EMPTY=1 SEED_DOWNLOAD_ASSETS=1 python scripts/seed_local.py &
fi

exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-10000}" --workers 2 --timeout 60 --access-logfile -
