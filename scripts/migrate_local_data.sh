#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
export POSTGRES_PASSWORD POSTGRES_DB POSTGRES_USER POSTGRES_HOST POSTGRES_PORT
legacy_source="${SEERKITCHEN_LEGACY_SOURCE:-$HOME/.seerkitchen/dev.sqlite3}"
if [ ! -s "$legacy_source" ]; then
  echo "No populated legacy SQLite file at $legacy_source; leaving PostgreSQL untouched."
  exit 0
fi
if uv run python manage.py shell -c 'from apps.tenancy.models import Tenant; assert not Tenant.objects.exists()' >/dev/null 2>&1; then
  :
else
  echo "PostgreSQL already has a kitchen. Refusing to merge two local data stores."
  exit 1
fi
work_dir="$(mktemp -d /private/tmp/seerkitchen-import.XXXXXX)"
chmod 700 "$work_dir"
trap 'rm -rf "$work_dir"' EXIT
export SEERKITCHEN_LEGACY_DB="$work_dir/legacy.sqlite3"
python3 - "$legacy_source" "$SEERKITCHEN_LEGACY_DB" <<'PY'
import sqlite3,sys
source=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro',uri=True)
target=sqlite3.connect(sys.argv[2])
source.backup(target)
target.close();source.close()
PY
DJANGO_SETTINGS_MODULE=config.settings.legacy_sqlite uv run python manage.py migrate --noinput >/dev/null
DJANGO_SETTINGS_MODULE=config.settings.legacy_sqlite uv run python manage.py export_legacy_data \
  --output "$work_dir/kitchen.json"
uv run python manage.py loaddata "$work_dir/kitchen.json"
uv run python manage.py shell -c 'from apps.tenancy.models import Tenant, BillingProfile; [BillingProfile.objects.get_or_create(tenant=t, defaults={"legal_name": t.name}) for t in Tenant.objects.all()]'
echo "Copied local kitchen data into PostgreSQL. Original SQLite is unchanged."
