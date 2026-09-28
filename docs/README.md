# SeerKitchen — docs

**[PLAN.md](PLAN.md) is the whole plan in one file** — business model, unit
economics, hosting, architecture, data model, current state, all seven phases,
traps and open decisions. Start there.

**[CODEBASE_STATUS.md](CODEBASE_STATUS.md) is the current implementation and
local-data inventory** — use it to see what exists now, what the development
database contains, and which risks remain before launch.

**[OPENCODE_STOREFRONT_HANDOFF.md](OPENCODE_STOREFRONT_HANDOFF.md) is the detailed
storefront and owner-CMS implementation backlog** — based on the September 2026
Sweet Karam Coffee review and the current source. It specifies the banner-led
store, editable homepage, missing commerce flows, implementation order, and
acceptance tests. It is a plan, not a claim that these features are implemented.

The files below are the detailed implementation specs PLAN.md links to.

---

## Build phases

Read `../AGENTS.md` first. It carries the conventions and the one invariant
that matters (tenant scoping). These documents assume it.

Work the phases in order. Each one is written to be finishable on its own and
ends in something demonstrable.

| Phase | Delivers | Why this order |
|---|---|---|
| 1 ✅ | Tenancy, fail-closed scoping, hostname routing | Everything depends on it |
| 2 ✅ | Catalog, scheduling, zones, storefront, CMS | The thing a customer sees |
| 3 | **Orders, Razorpay, invoices** | Nothing earns money until this works |
| 4 | Owner backend | What the client actually pays ₹5,000/month for |
| 5 | WhatsApp | The differentiator, but useless without 3 and 4 |
| 6 | Super admin and subscription billing | Needed before client #2, not before client #1 |
| 7 | Postgres and production deploy | Required by Phase 3; do the DB swap early |

Phases 4 and 5 can swap if you'd rather prove the WhatsApp story first. Nothing
else can move: 3 depends on 2, 5 depends on 3, 6 depends on nothing but is
pointless before there are clients to bill.

## Decisions already made

- `adr/0001-messaging-architecture.md` — the app owns messages; n8n, if used at
  all, is a per-tenant delivery driver behind one interface

## Definition of done, every phase

- `uv run pytest -q` green, including every behaviour listed in the phase doc
- `uv run python manage.py check` clean
- Migrations committed with the model changes
- No new cross-tenant query paths — the isolation tripwire still passes
- Anything a kitchen might want configured differently lives in `TenantConfig`

## A note on scope

Each doc has an **Out of scope** section. Respect it. The phases are sized so
each one finishes; pulling work forward is how a side project stalls.
