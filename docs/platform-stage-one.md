# Platform stage one: central accounts, kitchens and onboarding

## Restore point

The previous working application is preserved at Git tag
`pre-platform-2026-10-20`, commit `f194761`. The tag is pushed to GitHub. This is
an exact code restore point, not a backup of Render's live database.

A private archive of the onboarding machine's database was taken before the new
migration, at `/workspace/.cloud-setup/restore-points/pre-platform-2026-10-20/local-database.dump`.
Its archive index was checked with `pg_restore --list`. It contains local data,
not Render's production data; do not commit or publish it.

## Entry points

On the existing Render hostname, open `/platform/`. The public `/` storefront,
`/manage/`, `/billing/` and existing WhatsApp endpoints keep their current routing.
No new production domain or environment variable is required to try this stage.

- `/platform/login/`: central account login. Existing kitchen credentials work.
  Platform superusers open platform administration. One assigned kitchen opens
  its admin dashboard directly; multiple memberships show a kitchen picker
  whose links open each kitchen admin.
- `/platform/admin/`: superuser-only kitchen administration. Kitchen owners do
  not gain platform privileges because their username happens to be `admin`.
- `/platform/admin/kitchens/new/`: create a kitchen from a preset and invite its
  owner. Creation is transactional: failed setup does not leave partial tenants,
  accounts, domains or invitations.
- `/platform/workspaces/<slug>/`: owner workspace and setup checklist.
- `/platform/workspaces/<slug>/manage/`: the existing kitchen management tools.
- `/platform/workspaces/<slug>/billing/`: the existing billing portal.
- `/platform/workspaces/<slug>/preview/`: private website preview, available
  before any custom-domain/DNS work. Login and kitchen membership are required.

A configured `PLATFORM_HOST` also serves the platform landing page at `/`.
Do not change Annam's public hostname to the platform hostname merely to try this
feature: use `/platform/` on its existing host instead.

## One management login

`/platform/login/` is the sole platform/kitchen management login. Existing
credentials and roles are retained. `/manage/login/` and workspace-scoped
management login URLs are compatibility redirects, not separate login forms.
Old POSTs redirect without authenticating or copying credentials into a URL.
Management logout returns to the shared login. Saved management links preserve
their kitchen and query string only when the account is authorized for it;
otherwise the account's normal destination is used. Unassigned accounts see
an access-help screen, and inactive accounts cannot authenticate.

Billing keeps its existing login/form and credentials at `/billing/login/`.
Workspace billing links also use their own scoped billing login. That exact
anonymous authentication route is an exception to private workspace admission;
it serves no orders or invoices, and successful billing authentication still
requires membership in the selected kitchen. The login pages use the existing
Django session; this change does not introduce separate billing accounts or
customer authentication.

## Platform administrator account

Use a real Django superuser for platform administration. The existing seeded
kitchen owner is not automatically promoted. If no administrator account exists,
a developer with authorized Render shell access should run:

```bash
python manage.py createsuperuser
```

Enter the administrator's credentials interactively; never put them in Git or
send them in chat. This command must run against the intended deployed database.
A local superuser does not create a Render account.

The administrator can create kitchens, issue/reissue account invitations, assign
owner/manager/staff membership labels, change setup/active/suspended ordering
status, and configure existing website-ordering/courier-shop switches. Existing
kitchen tools currently grant access to all assigned kitchen members; the role
label does not yet introduce a separate granular permissions system. Platform
permissions remain superuser-only. Status/feature changes and invitations are
recorded in tenant-scoped platform audit events.

## Owner invitations

Creation returns a one-time invitation link. Copy and share it securely with the
intended recipient. Email sending is not configured or triggered automatically.
Only the token hash is persisted; raw invitation URLs cannot be retrieved later.
Reissuing invalidates previous unaccepted invitations for that user and kitchen.
Links expire after seven days and are invalid after acceptance.

A new owner account starts with an unusable password. Its invitation allows the
recipient to set a password validated using Django's password policy. An account
that already has a password must sign in as that account; an invitation does not
reset its password or log in a different existing user. Acceptance is locked in
a transaction so two simultaneous requests cannot set two different passwords.
Activation pages and invitation results are not cached and suppress cross-origin
referrers while preserving same-origin form submissions and CSRF checks.
The Render access-log format excludes query strings, so invitation tokens are
not recorded in request URLs by that launcher.

## Websites and subdomains

Creating a kitchen initializes its tenant, owner membership, billing/configuration
records, preset meal slots and draft content pages. It does not invent billing
registration numbers, connect payment accounts, send WhatsApp messages or charge
a subscription. New kitchens start in `provisioning`: public storefront ordering
is disabled until the administrator activates them.

`TENANT_BASE_DOMAIN` controls a reserved public subdomain:

- Development defaults to `localhost`, producing `kitchen-slug.localhost`.
- Production defaults to empty, leaving public domains unassigned while the
  owner uses the private workspace and preview.
- To use a domain you own, set a base such as `kitchens.example.com`. The app
  records `kitchen-slug.kitchens.example.com`; DNS, accepted hosting domains,
  Django `ALLOWED_HOSTS` and HTTPS must also be configured. A database mapping
  alone is not a verified live domain or certificate.

The subsequent [custom-domain settings](custom-domains.md) add ownership
verification, owner DNS instructions and explicit hosting/HTTPS connection.
Production connection stays disabled until the operator configures the edge. Existing tenant
custom domains continue to work. Never map an arbitrary customer-entered domain
without verification as a substitute for that later domain-management workflow.

## Workspace routing and tenant isolation

Each request determines its tenant independently; a session's last selected
kitchen is not trusted as an authorization decision. Workspace routes check an
active account and current membership (or platform superuser status) before
binding the tenant. The shared views run under that tenant and use scoped ORM
managers, forms, media authorization, and workspace-specific URL reversals.
Opening another kitchen in a browser tab cannot silently retarget the first tab.

Only explicitly configured platform hosts or already registered tenant hostnames
serve central routes. Unknown hosts still fail closed. Private workspaces do not
change the tenant used by `/manage/` or `/` on an existing public hostname.

Workspace WhatsApp connection settings use a tenant-specific public sync endpoint:
`/platform/webhooks/<slug>/whatsapp/n8n/`. Its bearer token is checked against that
kitchen's encrypted sync token. The corresponding signed Meta endpoint is
`/platform/webhooks/<slug>/whatsapp/`. Only those exact public webhook routes can
resolve a kitchen without a staff session; they do not expose workspace tools.
Existing host-based WhatsApp endpoints are retained for existing integrations.

## Deployment, checks and rollback

The new migration adds invitation and platform-audit tables. It does not rewrite
Annam's menus, configuration, orders, bills or secrets. `start.sh` already runs
migrations before serving; it continues supervising the web and inbox worker.

Validation covers existing storefront/owner/billing behavior plus central login,
platform-only permissions, kitchen provisioning, scoped tool routes, presets,
invitation activation/reissue/expiry, concurrent acceptance, CSRF, rollback on
setup failure and tenant-bound WhatsApp sync.

Release checks: 292 tests passed; Django system and migration checks passed.
The browser flow created a temporary kitchen, activated its owner, saved scoped
settings and checked role separation. Platform screens and shared tools were
checked at 320, 390, 768 and 1440 pixels. Temporary preview data was removed.

For a rollback, revert the platform change commit and deploy the revert. Keep
production backups and coordinate with the administrator before reverting any
database state. The old code can ignore the added tables; deleting new kitchens,
users or migrations is not necessary for a code rollback and would discard data.
Do not use `git reset --hard` or force-push `main` to restore the earlier version.

This stage does not implement Razorpay checkout, subscriptions, a full theme
builder or granular staff permissions. Custom-domain onboarding is covered in
[custom-domains.md](custom-domains.md). Those
remain independent stages after review of the central platform workflow.
