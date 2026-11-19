# Render PHP comparison preview

On the `php-rebuild` branch, the root `render.yaml` creates
`annam-foods-php-preview` and its own `annam-php-preview-db` in Singapore.
Choose **New → Blueprint → saran4125/annam_foods → php-rebuild**, file
`render.yaml`. Review the resources and Render's estimated price, then deploy.
The web service, persistent disk and database use paid plans. This does not
reference or modify the existing `annam-foods` / `annam-db` Python services.
The former Python demo Blueprint is retained as `render.python.yaml`.

After deployment open the new service URL followed by `/manage/login/` (or
`/billing/login/`). Username: `annam-php-owner`. The generated password is in
that service's **Environment → SEED_OWNER_PASSWORD**. Do not share it publicly.
It is set only at first initialization; later redeploys preserve changed accounts,
orders, catalog edits and uploaded media. Changing the seed variable later does
not reset the existing account's password.

Apache serves the PHP application, CSS and JavaScript. Python is installed only
for the startup schema migrations and existing catalog seeder; Django does not
serve requests. `APP_URL` is derived from Render's assigned hostname. Only
`php-app/public` is exposed, and uploaded photos/sessions/logs live on the disk.

This preview starts from the repository's reference catalog/settings, **not a
live database copy**. It contains no live customer/order history or integration
credentials. Bundled photos are restored; unavailable original photos may remain
missing. For exact data comparisons, arrange an explicit sanitized backup into
this preview database separately. Never point it at the existing production DB.
Startup refuses any database name other than `annam_php_preview`.

Real payments and outbound messaging stay disabled, and no worker/cron is
provisioned. Test manual orders, menus, billing and management actions here.
External-provider end-to-end acceptance is separate. Compare each management
tab with Python on desktop/mobile before declaring UI/function parity.

Build locally with `docker build -f Dockerfile.render-php -t annam-php-render .`.
The build context excludes local secrets, databases, uploads and runtime files.
