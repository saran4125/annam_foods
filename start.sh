#!/usr/bin/env bash
# Render start: migrate, load Annam on the very first boot only, then serve.
set -euo pipefail

# Explicit, temporary opt-in for the public PHP snapshot. Existing records stay
# unchanged. Remove this environment flag after a successful restore deployment.
restore_missing_php_data() {
  if [ "${RESTORE_MISSING_PHP_DATA:-0}" = "1" ]; then
    python manage.py restore_missing_php_data --tenant "${STORE_SLUG:-annam}" --apply
  fi
}

python manage.py migrate --noinput
python manage.py sync_annam_catalog --tenant "${STORE_SLUG:-annam}" --apply --if-provisioned
python manage.py apply_original_images
python manage.py materialize_media

# First boot: create the kitchen, its owner login, and download the catalog photos
# onto the persistent disk. SEED_ONLY_IF_EMPTY makes every later restart a no-op,
# so owner edits are never overwritten. Runs in the background so the site is
# already answering health checks while photos download.
export SEED_DOMAIN="${SEED_DOMAIN:-${RENDER_EXTERNAL_HOSTNAME:-}}"
if [ -n "${SEED_OWNER_PASSWORD:-}" ] && [ -n "${SEED_DOMAIN}" ]; then
  (
    SEED_ONLY_IF_EMPTY=1 SEED_DOWNLOAD_ASSETS=1 python scripts/seed_local.py
    python manage.py sync_annam_catalog --tenant "${STORE_SLUG:-annam}" --apply
    restore_missing_php_data
    python manage.py apply_original_images
    python manage.py materialize_media --download
  ) &
else
  (
    python manage.py sync_annam_catalog --tenant "${STORE_SLUG:-annam}" --apply
    restore_missing_php_data
    python manage.py apply_original_images
    python manage.py materialize_media --download
  ) &
fi

exec python scripts/serve_with_inbox.py
