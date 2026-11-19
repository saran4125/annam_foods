# Free Render PHP UI preview

On `php-rebuild`, the root `render.yaml` requests one **free Docker web service**,
`annam-foods-php-preview`. It requests no database, persistent disk or other paid
resource. Render can independently require account verification; this file cannot
bypass Render's account policies.

Choose **New → Blueprint → saran4125/annam_foods → php-rebuild**, path `render.yaml`.
Refresh/retry an older Blueprint review to load the latest commit. The resource
review should list only the free web service. Do not deploy `main` for PHP.

For a manually created Web Service use the same repo/branch, Docker runtime,
Dockerfile `./Dockerfile.render-php`, root context `.`, **Free** instance and health
path `/healthz`. Add `APP_SECRET`, `SECRET_KEY`, `SECRETS_KEY` and
`SEED_OWNER_PASSWORD` as distinct private random values (at least 32 characters),
`SEED_OWNER_USERNAME=annam-php-owner`, `STORE_SLUG=annam`, `PAYMENTS_ENABLED=0`,
`MESSAGING_ENABLED=0`, `REQUIRE_CRON=0`. Blueprint generates these secrets for you.
No database environment variables are needed.

Open the new service URL plus `/manage/login/` or `/billing/login/`. Username:
`annam-php-owner`; password: the service's **Environment → SEED_OWNER_PASSWORD**.
Never post this value publicly. Apache serves PHP. Python initializes an isolated
SQLite reference catalog at startup; Django does not serve requests. Only
`php-app/public` is web-accessible. Local build contexts exclude secrets/databases.

**Temporary testing only:** SQLite, uploaded images, sessions, test orders and
edits live under `/tmp/annam-php-preview`. They can disappear on redeploy, instance
replacement or restart. A new instance rebuilds the reference catalog and owner
login; do not enter real customer orders or rely on this for permanent storage.
The free service can sleep and take time to wake up. Payments/messages stay off.

The reference catalog/settings and bundled media come from this repository,
not a live Python database clone. Missing original photos and live history are
not supplied. Compare management UI/actions tab by tab on desktop and mobile.
The existing Python site/database are never connected or modified.

Local build: `docker build -f Dockerfile.render-php -t annam-php-render .`.

Public product/category/menu artwork and logos committed under `media/brand`,
`catalog`, `categories`, `menu` and `site` are included in the Docker image. Startup
restores missing files and assigns checksum-verified original photos to empty
catalog/category fields. Existing uploaded artwork takes priority. Private
`media/website` files and other upload folders remain excluded. The restore does
not download images, modify prices, or touch production data. Originals absent
from the public bundle remain unavailable.

New preview instances also apply the committed owner-reviewed catalog snapshot
and the original dated lunch/dinner and reviewed breakfast menus. Carry-forward
uses those saved dates; dated category names are not treated as a weekly plan.
This runs only once per newly initialized preview database, before staff edits.
Historical live orders, customers and invoices are not fabricated to match counts.
