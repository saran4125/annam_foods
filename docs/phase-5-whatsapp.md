# Phase 5 — WhatsApp

## Goal

A customer completes an entire order on WhatsApp, and it lands in the **same
order list** as a website order. `orders.channel = "whatsapp"` is the only
difference.

## Architecture decision, already made

**All logic is in the app. n8n, if a tenant uses it at all, only performs the
final send.** See `docs/adr/0001-messaging-architecture.md`.

The outbound half is **already built** — `apps/messaging/` landed with the
`OutboundMessage` queue, payload builders that enforce Meta's limits, retries
with backoff, `dedupe_key` idempotency, and three interchangeable senders
(`meta_cloud`, `n8n`, `console`) chosen per tenant by
`TenantSecrets.wa_provider`. Do not write another way to send a message.

This phase adds the **inbound** half and the conversation itself.

The lesson driving all of it: Annam's n8n Discovery flow reached 110 nodes, the
same `node hasn't been executed` bug was fixed three separate times, and six
weeks of changes sat un-imported. That is what business logic in a per-client
JSON file costs.

---

## Models — `apps/whatsapp/`

### `WaSession`
```
phone       CharField(20)
state       CharField(40)
data        JSONField(default=dict)
updated_at  DateTimeField
unique_together: (tenant, phone)
```
Conversation state lives here, in the database, not in a workflow engine.

### `WaInboundMessage`
```
phone           CharField(20), indexed
kind            CharField  text | button | list | location | order
body            TextField
raw             JSONField
wa_message_id   CharField(80), unique per tenant, indexed
at              DateTimeField
```
Inbound only. Outbound already lives in `messaging.OutboundMessage` — do not
duplicate it. The unique `wa_message_id` is the idempotency guard; Meta
redelivers.

`TenantSecrets` already carries `wa_phone_number_id`, `wa_waba_id`,
`wa_verify_token`, `wa_token` and `wa_app_secret`. Nothing to add.

---

## The webhook — `apps/whatsapp/views.py`

```
GET  /wa/<tenant_slug>/webhook    verification challenge (hub.challenge)
POST /wa/<tenant_slug>/webhook    inbound messages
```

```
1. resolve tenant from the slug
2. verify X-Hub-Signature-256 against that tenant's app secret — reject on fail
3. if WaMessage with this wa_message_id exists: return 200 (Meta redelivers)
4. normalise: text | button reply | list reply | location | order
5. load WaSession for (tenant, phone)
6. run the state machine -> list of outbound messages
7. queue the sends; persist the new state
8. return 200 fast — Meta times out and retries otherwise
```

Never call the Graph API inside the request. Queue it.

## State machine — `apps/whatsapp/flow.py`

Plain Python, no framework. A function per state:

```python
def handle(session, message) -> tuple[str, list[OutboundMessage]]:
    """Returns the next state and what to send. Pure — no I/O, no sends."""
```

Purity is the point: the whole conversation becomes table-driven tests with no
network and no database.

States:
```
IDLE           greeting or anything unmatched -> main menu
AWAIT_PINCODE  validate via delivery.services.zones_for_pincode
AWAIT_AREA     multi-zone pincode: which area
AWAIT_SLOT     which meal, honouring cutoffs
BROWSING       menu list, add items
AWAIT_ADDRESS  collect or confirm a saved address
AWAIT_CONFIRM  summary, confirm or cancel
AWAIT_PAYMENT  payment link sent, waiting on the Razorpay webhook
```

Reuse the existing services — `resolve_menu`, `zones_for_pincode`,
`create_order`. **Do not reimplement pricing or availability here.** If
WhatsApp and the website ever disagree about a price, this is why.

### Routing rules learned from Annam's bot

- An exact greeting keyword (`hi|hello|hey|start|menu`) matched as a **whole
  word at the start** of the message shows the main menu. `/^(HI|HELLO|...)\b/`
  — an exact-equality check broke on "Hello! Can I get more info?", and a naive
  substring match fires on "History".
- **Anything else unmatched** — a real question, gibberish — gets a contact
  fallback with the kitchen's phone number, *not* the menu again. A customer
  asking "do you deliver to Coimbatore" should not get a menu.
- Normalise pincodes through `delivery.services.normalise_pincode`; customers
  type "600 106".

## Sending — already done, just use it

```python
from apps.messaging import payloads as p
from apps.messaging.services import queue

queue(tenant, phone, p.buttons("Which meal?", [("lunch", "Lunch"), ("dinner", "Dinner")]),
      purpose="slot_prompt")
```

Available builders: `text`, `buttons`, `cta_url`, `list_message`, `document`,
`template`. Each validates Meta's limits at build time and raises
`PayloadError` — the 20-character `cta_url` label, 3 buttons, 10 list rows.
Those rules are tested in `apps/messaging/tests/test_payloads.py`; do not
re-check them in the flow code.

Use `queue()` on the webhook path so Meta gets its 200 immediately, and let
`send_pending_messages` deliver. `send_now()` exists for a request that can
afford to wait.

## The 24-hour window

Free-form messages only work within 24 hours of the customer's last message. A
payment confirmation lands fine; "out for delivery" three hours later may not.

Get four utility templates approved during onboarding, and treat approval as a
**provisioning step**, not an afterthought:
`order_confirmed`, `payment_received`, `out_for_delivery`, `delivered`.

Add `messaging.services.send_or_template(tenant, phone, free_form_payload,
template_name, params)` — picks based on the newest `WaInboundMessage` for that
phone. This is the one piece of the messaging spine Phase 5 still has to add.

## Transactional messages go straight from Django

Payment links, payment confirmations, invoice PDFs and the owner's new-order
alert are sent by the app in the order pipeline — not by the conversation
handler. An invoice must never fail to send because a conversation turn errored.

---

## Behaviours that must be tested

**Webhook**
- an invalid signature is rejected and changes nothing
- the same `wa_message_id` twice produces one `WaInboundMessage` and one
  queued reply — not two
- an unknown tenant slug 404s
- the GET challenge returns `hub.challenge` when the verify token matches

**Routing** (pure functions — table-driven, no network)
- "hi", "Hello!", "Hello! Can I get more info?" -> main menu
- "History", "Highway" -> **not** the menu (word-boundary guard)
- "do you deliver to Coimbatore" -> contact fallback, not the menu
- "600 106" and "600106" both resolve the same zone
- a multi-zone pincode asks for the area
- a slot past its cutoff is not offered

**Ordering**
- a completed WhatsApp conversation creates an `Order` with
  `channel="whatsapp"` that is otherwise identical to a website order
- it appears in the owner's order list alongside web orders
- prices come from `resolve_menu`, never from the session payload

**Message construction**
- already covered by `apps/messaging/tests/test_payloads.py`. What this phase
  must add: every payload the flow produces is built through
  `messaging.payloads`, never as a raw dict — so the limits actually apply

---

## Out of scope

Meta commerce catalog messages; voice notes; multi-language (Tamil is a Phase 6
config flag); WhatsApp Flows.
