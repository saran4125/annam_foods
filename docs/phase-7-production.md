# Phase 7 — Postgres and production

**Do the Postgres half of this before Phase 3**, not after. Invoice numbering
needs `SELECT … FOR UPDATE`, and SQLite cannot give you that. Everything else
here can wait until there's a client to deploy for.

## Goal

The app runs on Postgres locally and in production, on one server, serving
multiple kitchen domains with automatic TLS.

---

## 7a. Move to Postgres (do this first)

### Settings

Add `config/settings/prod.py` and switch `dev.py` to Postgres too, so dev and
prod agree. Read from environment:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}
```

Add `psycopg[binary]` to dependencies. Keep `.env` out of git; add
`.env.example` with every key and no values.

### What changes

- `JSONField` behaves better, not worse — no migration needed.
- The `MenuSchedule` partial unique indexes and check constraint work
  identically on Postgres. Re-run the constraint tests to confirm.
- `select_for_update()` starts actually locking. Phase 3 depends on this.

### Acceptance

- `uv run pytest -q` green against Postgres
- `apps/catalog/tests/test_constraints.py` still passes — the DB-level guards
  survived the move
- A fresh `migrate` on an empty Postgres database succeeds from zero

---

## 7b. Production settings

`config/settings/prod.py`:

- `DEBUG = False`, `SECRET_KEY` from env, `ALLOWED_HOSTS` from env
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
- `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`
- `CSRF_TRUSTED_ORIGINS` must include every tenant domain — build it from
  `TenantDomain` at startup, or accept a wildcard pattern per environment
- WhiteNoise for static files, or let Caddy serve `STATIC_ROOT`
- Structured logging to stdout

**Tenant domains and CSRF is the trap here.** Django checks `CSRF_TRUSTED_ORIGINS`
against a static list, but tenant domains are rows in a table. Load them at boot
and document that adding a domain needs a restart — or add a small middleware
that validates the origin against `TenantDomain` instead.

---

## 7c. Deploy

One server, Docker Compose. Target is a Hetzner CX33 (4 vCPU, 8 GB), but any
container host works.

```
services:
  web       gunicorn, 3 workers          mem_limit 750m
  worker    django-q2 / huey             mem_limit 500m
  db        postgres                      mem_limit 1g
  redis     redis                         mem_limit 128m
  caddy     reverse proxy, on-demand TLS  mem_limit 64m
```

Set `mem_limit` on every service from the start. On a 4 GB box an unbounded
service that OOM-kills Postgres mid-service is the outage you don't want. Add a
2 GB swap file as a backstop and put Postgres data on its own volume.

Postgres tuning for a small box: `shared_buffers` 512 MB, `max_connections` 40.
Django with `CONN_MAX_AGE` does not need 100.

### Caddy and tenant domains

Use **on-demand TLS** so a certificate is issued automatically for any client
domain pointed at the server, with an `ask` endpoint so Caddy only issues for
hostnames you recognise:

```
{
  on_demand_tls {
    ask http://web:8000/internal/tls-check
  }
}

:443 {
  tls { on_demand }
  reverse_proxy web:8000
}
```

Add `GET /internal/tls-check?domain=…` returning 200 if a matching
`TenantDomain` exists and 404 otherwise. Without the `ask` guard, anyone
pointing a domain at your IP makes you issue them a certificate.

### Backups — not optional

Self-hosted Postgres means backups are entirely yours.

- Nightly `pg_dump` to object storage, with versioning
- **A restore you have actually performed once**, before any client data exists
- Losing a kitchen's order and invoice history ends the client relationship
  permanently and follows your name around a small industry

### Trigger to move off the single box

Write it down now so it isn't an emotional decision later: **at three paying
clients, move Postgres to managed hosting** for automated backups and
point-in-time recovery. At that point one instance carries ₹15,000/month of
revenue and ~$25 for real backups is insurance, not a cost.

---

## Acceptance

- Two tenant domains resolve to their own storefronts over HTTPS on one server
- An unknown domain gets no certificate and no site
- `pg_dump` runs nightly and a restore has been tested end to end
- Deploy is one command and does not involve editing files on the server
