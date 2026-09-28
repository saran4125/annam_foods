# WordPress storefront preview

This directory is the independent Annam storefront prototype described in
`docs/PLAN.md` §4.2. It has no sync with Django and does not submit orders.
WordPress Multisite owns its own product catalog, media, content and preview
carts. The active master plan still puts production billing in Django; do not
enable checkout or point Annam's public DNS here until the architecture is
decided and the payment/order path is built.

## Start locally

```bash
bash wordpress/scripts/dev.sh
python3 wordpress/tests/http_checks.py
docker compose -f wordpress/compose.yaml run --rm -T cli \
  eval-file /opt/seer/tests/behaviour.php --url=http://demo.localhost:8090
```

The bootstrap script generates `wordpress/.env` with local owner passwords
when needed. It builds pinned WordPress, WooCommerce, MariaDB and Caddy
images; creates `seer.localhost`, `annam.localhost` and `demo.localhost` sites;
extracts the public Annam catalog over valid HTTPS; reports proposed import
changes; applies the first import; and seeds Annam's homepage only once.
Product photos are copied into Annam's site-specific WordPress media library.
The image-generation campaign artwork in `data/artwork/` is separate from
those unmodified product photos.
The page-by-page visual findings and fixes are recorded in
`reports/UI_REVIEW.md`.

- Storefront: `http://annam.localhost:8090/`
- Owner editor: `http://annam.localhost:8090/wp-admin/`
- Separate demonstration store: `http://demo.localhost:8090/`
- Local owner logins: `annam-owner` and `demo-owner`; passwords in the ignored
  `wordpress/.env` file.

## Repeat a catalog import safely

```bash
python3 wordpress/scripts/fetch_annam.py
wordpress/scripts/wp.sh seer import --url=http://annam.localhost:8090 \
  --report=/opt/seer/reports/annam-import-plan.json
```

The first command refreshes the public source manifest and images. The second
is a dry run. It reports source failures, new items, changes, duplicates, and
owner edits. `--apply` imports new and unedited rows while preserving owner
conflicts. To explicitly overwrite conflicts, review the exact dry-run JSON,
then pass `--apply --approve-report=/opt/seer/reports/annam-import-plan.json`.
A changed source, site or local state invalidates that approval digest.

Draft products and policy pages require owner review before publishing. Annam
has no inferred delivery dates, zones or meal windows. The demonstration
store's lunch window and pincode are marked test fixtures. Checkout, orders,
payments and production activation remain disabled.

## Add another site

Configure the domain in `config/Caddyfile` and `SEER_ALLOWED_HOSTS` in the
ignored `.env`, then reload Compose. Create a site with the platform-only CLI:

```bash
wordpress/scripts/wp.sh seer provision \
  --domain=newstore.localhost:8090 --name="New store" \
  --owner=newstore-owner --email=owner@example.test
```

The command writes a mode-0600 credential file to `wordpress/reports/`. The
owner can edit layouts, navigation, typography, imagery, products and pages
through WordPress/WooCommerce. SEER controls software installation and
updates; the `SeerKitchen Core` must-use plugin cannot be disabled per site.
For a production custom domain, provision the site with that exact domain,
configure its HTTPS Caddy stanza, then verify DNS and certificate issuance.

## Current limitations

Three public source categories failed their catalog API response during the
latest extraction; the importer records them in its report. Campaigns and
policy text from the old site stay drafts until reviewed. The WordPress
preview and Django production plan are separate order systems by design
pending the architecture decision; do not run live checkout on either side of
this prototype.
