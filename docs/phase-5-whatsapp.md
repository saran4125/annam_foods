# Phase 5 — WhatsApp

## Goal

A customer completes an entire order on WhatsApp, and it lands in the **same
order list** as a website order. `orders.channel = "whatsapp"` is the only
difference.

## Architecture decision, already made

**No n8n.** Meta posts webhooks directly to Django. The conversation state
machine is Python, with tests.

The earlier plan had a thin n8n relay. It was dropped because it is one view
and a helper function in Python, costs ~700 MB of RAM on a shared box, adds a
second place to debug, and makes every new client a workflow import instead of
a database row. n8n stays in production for the older AVR / DHC / TailorsKart
builds; it is not part of this product.

The lesson driving this: Annam's n8n Discovery flow reached 110 nodes, the same
`node hasn't been executed` bug was fixed three separate times, and six weeks
of changes sat un-imported. That is what business logic in a per-client JSON
file costs.

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

### `WaMessage`
```
phone           CharField(20), indexed
direction       CharField  in | out
type            CharField  text | interactive | template | document
body            TextField
wa_message_id   CharField(80), blank, indexed
status          CharField  queued sent delivered read failed
error           TextField, blank
at              DateTimeField
```
The inbound log doubles as the idempotency guard — Meta redelivers.

Add to `tenant_secrets`: `wa_phone_number_id`, `wa_token_enc`, `wa_waba_id`,
`wa_app_secret_enc`, `wa_verify_token`.

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

## Sending — `apps/whatsapp/client.py`

```python
def send_text(tenant, phone, body) -> str
def send_buttons(tenant, phone, body, buttons)      # max 3
def send_list(tenant, phone, body, sections)        # max 10 rows
def send_cta_url(tenant, phone, body, url, label)   # label <= 20 chars
def send_document(tenant, phone, url, filename)     # invoices
def send_template(tenant, phone, name, params)      # outside the 24h window
```

**Meta's limits, each of which cost Annam a live outage:**
- `cta_url` button text is **20 characters maximum**. A 26-character label
  silently failed every "Place Order" tap for days. Validate in code and test
  the boundary.
- Only one URL per message. Interactive list and button payloads cannot carry
  a link at all.
- Button messages cap at 3 buttons; lists at 10 rows.

## The 24-hour window

Free-form messages only work within 24 hours of the customer's last message. A
payment confirmation lands fine; "out for delivery" three hours later may not.

Get four utility templates approved during onboarding, and treat approval as a
**provisioning step**, not an afterthought:
`order_confirmed`, `payment_received`, `out_for_delivery`, `delivered`.

Helper: `send_or_template(tenant, phone, free_form, template_name, params)` —
picks based on the last inbound `WaMessage` timestamp.

## Transactional messages go straight from Django

Payment links, payment confirmations, invoice PDFs and the owner's new-order
alert are sent by the app in the order pipeline — not by the conversation
handler. An invoice must never fail to send because a conversation turn errored.

---

## Behaviours that must be tested

**Webhook**
- an invalid signature is rejected and changes nothing
- the same `wa_message_id` twice produces one `WaMessage` and one reply set
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
- every `cta_url` label is ≤ 20 characters — assert the boundary
- button messages never exceed 3 buttons, lists never exceed 10 rows

---

## Out of scope

Meta commerce catalog messages; voice notes; multi-language (Tamil is a Phase 6
config flag); WhatsApp Flows.
