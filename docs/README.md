# SeerKitchen — docs

**[PLAN.md](PLAN.md) is the whole plan in one file and the single source of
truth** (v2, 28 September 2026): what we are building and why, the
plug-and-play customisation model, the complete WhatsApp specification
(parity with Annam's bot, ordering in chat and from the catalog, payments,
updates), invoicing — bills for every order however it was placed, sent on
WhatsApp and available on request — the data model, the build phases A–H, the
Annam migration, risks and open decisions. Start there.

Read `../AGENTS.md` before writing code. It carries the conventions and the one
invariant that matters (tenant scoping).

## Supporting documents

Where any of these differ from PLAN.md, **PLAN.md wins**.

| Document | Use it for |
|---|---|
| [adr/0001-messaging-architecture.md](adr/0001-messaging-architecture.md) | Decision record, in force: the app owns every message; n8n is at most a delivery driver |
| [n8n/wa-send-workflow.md](n8n/wa-send-workflow.md) | The optional n8n sender |
| [CODEBASE_STATUS.md](CODEBASE_STATUS.md) | Snapshot inventory of the code and local data (PLAN.md §4 is newer) |
| [OPENCODE_STOREFRONT_HANDOFF.md](OPENCODE_STOREFRONT_HANDOFF.md) | Detailed storefront and owner-CMS fix list and backlog |
| `phase-3` … `phase-7` | Earlier per-phase implementation notes, reused by PLAN.md §17 |
| [storefront-redesign.md](storefront-redesign.md) | Historical note |

## Definition of done, every phase

- `uv run python -m pytest -q` green, including every behaviour listed for the
  phase
- `uv run python manage.py check` clean
- Migrations committed with the model changes
- Isolation tripwire passes; no tenant slug in `apps/`
- Anything kitchen-specific is a setting, flag, copy key or preset — never code
- PLAN.md updated where reality differed
