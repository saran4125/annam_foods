#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  umask 077
  python3 - <<'PY' > .env
import secrets
for key in ('DB_PASSWORD', 'DB_ROOT_PASSWORD', 'SEER_ADMIN_PASSWORD', 'ANNAM_OWNER_PASSWORD', 'DEMO_OWNER_PASSWORD'):
    print(key + '=' + secrets.token_urlsafe(24))
PY
fi
docker compose up -d --build
docker compose exec -T wordpress sh -c 'until test -f wp-config.php; do sleep 1; done'
set -a
source .env
set +a
wp() { docker compose run --rm -T cli "$@"; }
if ! wp core is-installed --network >/dev/null 2>&1; then
  wp core multisite-install --url=http://seer.localhost:8090 --title=SeerKitchen --admin_user=seer --admin_password="$SEER_ADMIN_PASSWORD" --admin_email=platform@example.test --subdomains --skip-email
fi
wp plugin install woocommerce --version=11.1.2 --activate-network
wp eval-file /opt/seer/scripts/provision.php
wp option update woocommerce_coming_soon no --url=http://annam.localhost:8090
wp option update woocommerce_coming_soon no --url=http://demo.localhost:8090
wp eval-file /opt/seer/scripts/seed-demo.php --url=http://demo.localhost:8090
if [ ! -f data/catalog.json ]; then python3 scripts/fetch_annam.py; fi
wp seer import --url=http://annam.localhost:8090
wp seer import --apply --url=http://annam.localhost:8090
wp eval-file /opt/seer/scripts/seed-annam-home.php --url=http://annam.localhost:8090
printf '\nAnnam: http://annam.localhost:8090\nDemo: http://demo.localhost:8090\nOwner editor: /wp-admin/\nLocal credentials: wordpress/.env (never commit)\n'
