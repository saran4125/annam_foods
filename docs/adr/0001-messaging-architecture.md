# ADR 0001 — The app owns messages; n8n is a driver

**Status:** accepted
**Date:** 2026-08-29

## The question

Should WhatsApp messages be composed and sent by the app, or should the app
ask n8n to send them?

## Context

Annam's bot is 110 nodes of n8n. The same `node hasn't been executed` bug was
fixed three separate times, six weeks of changes sat un-imported, and a
26-character button label silently killed every "Place Order" tap for days
because the failure lived in an execution log nobody was watching.

The proposal was: keep all logic in the app, and have the app POST to n8n when
it wants a message sent — "the app says what to send, n8n sends it."

The instinct is right. Taken literally it has one flaw: **the app can no longer
answer "did the customer get their invoice?" without reading someone else's
execution log, and a dead n8n loses the message rather than delaying it.** That
is the Annam failure mode with a new shape.

## Decision

The app owns the *message*. n8n, when used, owns only the *final hop*.

```
service code
   └─ payloads.py      builds a provider-agnostic payload, validates Meta's limits
   └─ services.queue() writes an OutboundMessage row  ← the source of truth
   └─ worker
        └─ sender_for(tenant)
             ├─ MetaCloudSender  → Graph API          (default)
             ├─ N8nSender        → n8n webhook → Meta (opt in, per tenant)
             └─ ConsoleSender    → the log            (development)
```

`TenantSecrets.wa_provider` picks the driver **per tenant**, so one kitchen can
run through n8n while another goes direct, with no code change.

### What stays in the app, always

- What to say, and to whom
- Validation of Meta's limits — the 20-character `cta_url` label, 3 buttons,
  10 list rows — enforced once, in `payloads.py`, so the rules hold whichever
  driver delivers
- The queue, retries with backoff, and the give-up rule
- Idempotency, via `dedupe_key`, so a redelivered payment webhook cannot send
  two invoices
- The record of what happened: status, attempts, error, provider message id

### What n8n gets

An HTTP POST containing the message and a ready-made `graph` object it can
forward to Meta unchanged. The workflow needs no logic — see
`docs/n8n/wa-send-workflow.md`.

## Consequences

**Good.** One place to look when a client asks whether a message went out,
regardless of how it was sent. Meta's limits can't be violated by one path and
not the other. n8n can be adopted or dropped per tenant as a setting. A dead
n8n produces a delayed message, not a lost one — the row stays `failed` and is
retried. Tests run against a fake sender, so none of this needs a network.

**Costs.** An `OutboundMessage` table that grows and needs pruning. Two layers
to read when debugging a send. `to_graph_payload` has to be kept correct as
Meta's API evolves — though that is true of the n8n workflow too, and here it
has tests.

**Rejected: app → n8n as the only path.** It makes n8n a hard dependency of
every transactional message, including invoices, and moves the answer to "did
it send?" outside the product.

**Rejected: conversation logic in n8n.** That is what produced the 110-node
workflow. Phase 5 keeps the state machine in Python, as pure functions.

## Default

New tenants start on `console` (nothing is sent until deliberately configured).
Production tenants should default to `meta_cloud` — the fewest moving parts.
Choose `n8n` when a client's sending genuinely needs to live in a workflow: an
existing setup you don't want to disturb, or a different BSP.
