# Annam production hardening — 2 November 2026

This release improves application security, recovery, worker reliability and
query behaviour. It is **not a claim that a live deployment is bug-free**.
No production credentials, provider messages, payments or restore operations
were used during verification.

## Implemented and verified

| Area | Change |
|---|---|
| Staff access | Database-backed login throttling shared by management/billing and all web workers. Twenty attempts per client address per five-minute window; lookup requests have their own bound. Counters store hashed identities, not raw IPs or customer numbers. |
| Private data | Staff/billing responses explicitly private and no-store, with Cookie variation and noindex headers. Error reports omit POST bodies, query strings, authorization headers and frame locals. |
| Public uploads | Only image extensions are publicly served. Traversal, links outside the media root, and aliases into the protected website library are rejected. |
| Dependencies | Pillow upgraded from 12.3.0 to patched 13.0.0 after the scanner reported vulnerabilities. Django constrained to the 5.2 LTS line; production cryptography minimum aligned with the tested development version. Python 3.11+ is now required; the deployed Python 3.12 remains supported. |
| Backups | Streaming AES-256-GCM authenticated encryption covers a PostgreSQL custom dump, public images, private bills and application recovery keys. Each file is checksummed; the encrypted archive is verified before publication. Existing snapshots cannot be overwritten; public backup destinations and source symlinks are rejected. |
| Off-site copy | Optional authenticated, streamed upload to a configured private Supabase Storage bucket. Failures keep the local encrypted copy and report an unconfirmed upload. No off-site account was configured or contacted during testing. |
| Runtime | Inbox iterations recover from exceptions with bounded backoff; successful work writes a heartbeat. Readiness checks database, writable storage and, when required, heartbeat freshness. Supervisor shutdown tolerates child exit races. |
| Scheduled work | The inbox worker now performs the daily handoff and removes expired rate windows. Transactional provider dispatch stays **disabled by default** until explicitly enabled. Existing provider settings/held drafts are not activated. |
| Capacity | Category family totals are computed in memory from grouped queries instead of queries per row. Shop pages are bounded at 36 products. Recent order listings have a tenant/date index. Gunicorn workers/threads are configurable, with bounded request recycling. PostgreSQL connection health checks, connect timeout, query timeout and lock timeout are configured. |
| Release checks | GitHub Actions runs PostgreSQL tests, migration consistency and dependency auditing. Production deployment/branch-protection rules must be configured externally to require these checks. |

## Evidence

- **643 PostgreSQL tests passed**, including concurrent rate-limit enforcement,
  tamper rejection, historical workflow regressions and query-count budgets.
- **7 browser checks passed**: private responses, shared login throttle,
  shop pagination, readiness and mobile layout.
- Installed-package vulnerability audit: **no known vulnerabilities found**
  after the Pillow update. This is a point-in-time advisory scan, not a complete
  security certification.
- Actual encrypted local backup restored into a new disposable PostgreSQL
  database, with migration/catalog counts verified; image, private bill and
  recovery keys also matched. The scratch database was then dropped.
- Two-worker local GET smoke: **100 requests, concurrency 8, zero errors**;
  median **84.43 ms**, p95 **173 ms**. This is a local smoke result, not a
  production traffic-capacity claim or a test of live payments/WhatsApp.

Reports: [restore drill](review/restore-drill.json),
[dependency audit](review/dependency-audit.json),
[load smoke](review/load-smoke.json),
[browser checks](review/browser-checks.json).

## Hosting changes still required

The currently offered free Render profile uses temporary media storage. Code
cannot turn that into a durable disk. The paid profile now enables the durable
storage guard and `/readyz` checks, but this release does not purchase a plan,
attach a disk, modify live secrets or change the current hosting account.

For a durable single-instance deployment configure:

```text
PUBLIC_MEDIA_ROOT=/var/data/media
PRIVATE_BILLS_ROOT=/var/data/private-bills
STORAGE_PERSISTENT=1
REQUIRE_DURABLE_STORAGE=1
READINESS_CHECK_STORAGE=1
REQUIRE_WORKER_HEARTBEAT=1
POSTGRES_SSLMODE=require
WEB_CONCURRENCY=2
WEB_THREADS=2
```

Use an actual persistent `/var/data` volume and confirm a newly uploaded image
survives redeployment. The guard refuses a declared production profile using
`/tmp` storage. `STORAGE_PERSISTENT=1` is an operator declaration; it does not
prove the host mounted a durable disk. A mounted disk is not a backup and does
not enable horizontal media sharing across instances.

TLS is required by default for the production database. Prefer `verify-full`
with the provider's CA (`PGSSLROOTCERT`) when available. Keep `SECRET_KEY` and
`SECRETS_KEY` stable in the private environment. Sessions use secure/HttpOnly
cookies and expire after eight hours. Host/origin lists in the paid template
are narrowed to the service; add only the actual deployed/custom hostnames.

Only set `TRUSTED_PROXY_HOPS` when the hosting gateway's forwarded-address
behaviour is verified. Default 0 ignores spoofable forwarded headers. HSTS
preload and include-subdomains are intentionally not forced: enabling them
requires checking every affected domain/subdomain and is not part of this
release.

## Private backup configuration

Install a `pg_dump` client compatible with the database server version in the
backup environment (or supply `PG_DUMP_BIN`). The restore drill used PostgreSQL
17 tools through the local Docker service; this does not install a client on
Render. The backup job must see the actual public-media and private-bill roots.

Configure these privately; never paste keys into GitHub, logs or public forms:

```text
BACKUP_ENCRYPTION_KEY=<separate base64-encoded 32-byte random key>
BACKUP_SUPABASE_URL=https://<project>.supabase.co
BACKUP_SUPABASE_BUCKET=annam-backups
BACKUP_SUPABASE_TOKEN=<backend-only storage upload credential>
```

Create the Supabase bucket as **private**, with access restricted to the backup
operator. Keep a separate recovery copy of the backup encryption key outside
the hosting account. Retain older keys for older snapshots after rotation.
Application encryption/signing keys are inside the encrypted archive so tenant
credentials remain recoverable; the backup encryption key is never included.

Create and verify a uniquely named snapshot:

```bash
python manage.py backup_store --output /var/data/backups/annam-YYYYMMDD-HHMMSS.enc
python manage.py verify_store_backup /var/data/backups/annam-YYYYMMDD-HHMMSS.enc
```

With the private bucket configured, create and upload in one operation:

```bash
python manage.py backup_store --output /var/data/backups/annam-YYYYMMDD-HHMMSS.enc --upload
```

Retry a failed upload without recreating/overwriting the snapshot:

```bash
python manage.py upload_store_backup /var/data/backups/annam-YYYYMMDD-HHMMSS.enc
```

A success means the remote API acknowledged the upload, not that a production
restore has been performed. Download and verify an off-site copy as part of
acceptance. Configure a daily job in a backup-capable environment with the same
media volume, failure alerts and off-site retention (for example seven daily
and four weekly copies). No recurring live job or retention policy has been
installed by this code release. Keep local encrypted copies until off-site
verification succeeds. Avoid unrelated file maintenance during a snapshot;
PostgreSQL is consistent, while file storage is copied separately.

## Restore runbook — always rehearse in an isolated environment

1. Download the encrypted archive from the private bucket and supply its matching
   `BACKUP_ENCRYPTION_KEY` privately.
2. Authenticate it before attempting recovery:

   ```bash
   python manage.py verify_store_backup /private/snapshot.enc --extract-to /private/empty-recovery-directory
   ```

   The destination must be empty and outside public/live storage. Files are
   extracted only after authentication and checksum verification; recovery
   files are owner-readable only. This command never overwrites a database.
3. Create a new scratch PostgreSQL database. Point `PGHOST`, `PGPORT`, `PGUSER`
   and credentials to that isolated target; do not point at the live database.
   Restore `meta/database.dump` with `pg_restore --single-transaction --no-owner
   --no-acl --dbname <new-scratch-database>` using a compatible client.
4. Copy `public-media/` and `private-bills/` to separate empty test storage roots.
   Load keys from `meta/recovery.json` into the test secret manager privately.
   Preserve the application encryption key to decrypt saved provider settings.
5. Start an isolated app with external sending/payments disabled. Verify customer
   and order counts, bill totals, sample images, private bill permissions and
   credential decryption. Record the recovery time and missing data window.
6. Delete the disposable target after review. A real production cutover requires
   a maintenance window, a final current backup and a separately authorized plan.

## Monitoring and scalability acceptance

- `/healthz`: inexpensive database liveness probe.
- `/readyz`: minimal no-store readiness response; optional durable-storage and
  worker freshness checks. It reveals no customer data, host paths or credentials.
- Configure host uptime alerts and verify an alert reaches the operator when the
  app/worker fails. The app cannot prove alert delivery without the live account.
- Run `python manage.py check_store_operations --strict` on the deployed service.
  It reports configuration gaps without printing secret values. A successful
  configuration check still requires the external tests listed above.
- Expired throttling counters are cleared by worker maintenance; the manual
  command is `python manage.py prune_operation_limits`.
- Keep `ENABLE_TRANSACTIONAL_MESSAGES=0` while provider integration remains
  offline. Enable it only after validating credentials, consent, webhook
  authentication and retry/deduplication behaviour in the provider environment.
- Benchmark an authorized staging deployment with
  `python scripts/load_smoke.py --base-url https://<staging-host> --requests 100 --concurrency 8`.
  This script performs only bounded public GET requests. Test realistic checkout
  and webhook traffic separately with test accounts and no real charges/messages.
- Review CPU/RAM, response percentiles, database connection limits and query
  plans before increasing workers. Each instance uses roughly workers × threads
  web connections plus background connections; coordinate with the provider's
  pool/connection cap.
- Horizontal scaling additionally requires shared durable media, database-backed
  sessions, shared PostgreSQL throttling and controlled worker roles. Large sales
  exports and high-volume provider flows still need production-sized load tests.
  Do not infer a supported concurrency level from the local smoke numbers.
