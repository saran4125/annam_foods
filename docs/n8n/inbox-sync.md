# WhatsApp inbox and the existing n8n automation

The staff inbox is `/manage/whatsapp/` on the kitchen's own domain. It is
independent of the separate `/billing/whatsapp/` billing section. Staff sign in
with the existing `/manage/` account. New conversations, incoming catalog carts,
text, interactive replies, attachments and outgoing message statuses appear here.
Messages are tenant-scoped and deduplicated by Meta's message ID.

No live WhatsApp subscription, n8n workflow or credentials are changed by a Git
deployment. Complete the connection below; do not enter secrets in chat or Git.
Only newly delivered/copied events are captured. Meta does not supply old chat
history or outgoing Cloud API message bodies through delivery callbacks.

## 1. Connection settings

Open `/manage/whatsapp/settings/`. Set:

- **Meta phone number ID:** the numeric ID, not the visible WhatsApp phone number.
- **WABA ID:** optional; if set, forwarded events must carry the matching entry ID.
- **Staff reply sender:** **Keep n8n automation**.
- **n8n inbox sync token:** a fresh random secret of at least 24 characters. Save
  the same value in n8n Header Auth, header `Authorization`, value `Bearer <token>`.
- **n8n send workflow URL:** the production HTTPS Webhook URL of the send workflow
  described in [wa-send-workflow.md](wa-send-workflow.md). Staff replies use that
  workflow, not a separate direct-Meta send implementation.
- **n8n workflow bearer token:** configure the same Header Auth on the n8n send
  workflow, and on its optional receive webhook. This is distinct from the inbox
  sync token above: one protects n8n, the other protects this platform.
- **Meta access token:** optional for n8n sending, required for image/audio/video
  previews and document downloads. Media is fetched server-side from Meta only
  after staff authorization; the token is never sent to the browser.

Secret fields are write-only and encrypted where supported by `TenantSecrets`.
Leave them blank to retain their saved values. Keep Render's `SECRETS_KEY` stable.
Changing phone number IDs or accounts does not import historical conversations.

## 2. Recommended: leave the existing Meta → n8n subscription in place

Add a branch immediately after the existing WhatsApp Trigger/Webhook. POST each
incoming event **and status event** to:

```
POST https://annam-foods.onrender.com/webhooks/whatsapp/n8n/
Authorization: Bearer <inbox-sync-token>
Content-Type: application/json
```

Use the URL displayed by this kitchen's connection settings if the domain changes.
Body when the full original Meta webhook is available:

```json
{
  "event": "meta",
  "payload": {
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "YOUR_WABA_ID",
      "changes": [{
        "field": "messages",
        "value": {
          "metadata": {"phone_number_id": "YOUR_PHONE_NUMBER_ID"},
          "contacts": [{"wa_id": "919999999999", "profile": {"name": "Customer"}}],
          "messages": [{
            "from": "919999999999", "id": "wamid.from-meta",
            "timestamp": "1792483200", "type": "text",
            "text": {"body": "Two lunch meals please"}
          }]
        }
      }]
    }]
  }
}
```

Those are example IDs/numbers/timestamps, not credentials or events to send.
Pass the actual webhook payload unchanged; do not rebuild live message IDs.
If n8n's WhatsApp Trigger already unwrapped `entry[].changes[].value`, wrap its
output in the `object/entry/changes/value` structure above. Preserve `metadata`,
`contacts`, `messages`, `statuses` and the original timestamps. The optional WABA
setting must match the entry ID. Incoming status callbacks use the same structure
with `statuses` in `value`, instead of `messages`.

Use an **HTTP Request** node with JSON body
`{{ { event: 'meta', payload: $json.body ?? $json } }}` only when that node receives
the full Meta webhook. Otherwise add the wrapper first. Use stored Header Auth
credentials, not token literals in exported nodes. Retry the sync node on errors;
keep this copy separate from the automation's main branch.

This sync route **does not forward back to n8n**, preventing a forwarding loop.
Existing automation continues responding exactly as it did before this inbox.

## 3. Copy every message sent by n8n

After each successful send to Meta, add a separate inbox-sync HTTP Request node.
Include both the Graph request body and Meta's returned `messages[0].id`:

```json
{
  "event": "outbound",
  "phone_number_id": "YOUR_PHONE_NUMBER_ID",
  "message_id": "wamid.returned-by-meta",
  "timestamp": "ACTUAL_UNIX_SECONDS",
  "contact_name": "Optional customer name",
  "message": {
    "messaging_product": "whatsapp",
    "to": "919999999999",
    "type": "text",
    "text": {"body": "Your order is confirmed."}
  }
}
```

`message` is the exact Graph request that was successfully sent, including
interactive, template or document bodies. `timestamp` may be omitted to use
receipt time, or set to `String(Math.floor(Date.now() / 1000))`. Example n8n JSON
expression (adapt the node names to the actual workflow):

```javascript
{{ {
  event: 'outbound',
  phone_number_id: 'YOUR_PHONE_NUMBER_ID',
  message_id: $('Send to Meta').first().json.messages[0].id,
  timestamp: String(Math.floor(Date.now() / 1000)),
  message: $('Build Graph Message').first().json.graph
} }}
```

Reuse the same inbox-sync endpoint and Header Auth. Retry **only the copy node**
if synchronization fails; do not resend the Graph message. Replaying the same
provider ID is safe. Delivery/read/failed receipts can arrive before the outgoing
copy; their stored state is applied when its body arrives.

Staff replies are already recorded when queued in the app. The n8n send workflow
should return `{ "wamid": "..." }`; an outgoing copy with that ID is merged into
its existing bubble, not shown twice. Other transactional app messages are also
mirrored into conversation history.

## 4. Optional: give Meta the platform callback URL

If you deliberately move Meta's subscription here:

```
Callback URL: https://annam-foods.onrender.com/webhooks/whatsapp/
Verify token: the value you entered in the connection form
Subscription field: messages
```

Before changing Meta, set **Meta app secret** and **Verify token** in connection
settings. Verification echoes `hub.challenge` only for the correct saved token.
POSTs require a valid HMAC-SHA256 `X-Hub-Signature-256` over the unmodified body.
The body is never trusted based on a tenant ID from the sender: the host and
configured Meta phone ID select this kitchen.

To preserve automation, add a **separate HTTP Webhook** entry to the existing n8n
workflow and save its production HTTPS URL as **n8n automation receive URL**.
Use Header Auth with the workflow bearer token. This is not the old WhatsApp
Trigger URL. The forwarded body is the verified Meta `object/entry` payload,
filtered to this kitchen; access it as `$json.body` in n8n's HTTP Webhook node.
Connect it to the same normalization/automation logic used by the original trigger.

Acknowledge immediately with 2xx; run long automation after acknowledgement.
Deduplicate on incoming message ID or `X-SeerKitchen-Event-ID`, because forwarding
has bounded retries and a crash after n8n accepts an event can cause redelivery.
Do not run both trigger paths for the same incoming message without deduplication.
The inbox worker durably retries forwarding; five failed attempts become a visible
failed forwarding count in connection settings. After fixing the workflow, replay
that event from n8n/Meta or inspect it through an authorized Django shell.

Continue the outgoing sync branch from §3: Meta's status webhook alone does not
supply the outgoing body.

## Replies, order entry and operations

- Free-text staff replies require a customer message within the last 24 hours.
  Closed windows are blocked at queue time and rechecked before delivery.
  Sending approved templates outside that window remains in the existing provider
  workflow; copied template messages still appear in the inbox.
- Staff replies are queued, then dispatched through `apps.messaging` and the
  configured sender. Status is shown as pending/sending/sent/failed/read; the
  inbox never treats queueing as confirmed delivery. Do not configure display-only
  as a production sender.
- **Create order** opens WhatsApp billing entry with the customer's name/phone
  prefilled. A message/catalog cart is an order request, not a verified paid order.
  Staff select catalog items; billing still requires confirmed payment.
- Media previews require a valid Meta access token. No token or an expired media
  ID is shown as unavailable; credentials are not embedded in image URLs.
- The inbox refreshes every five seconds while visible. It keeps reply drafts and
  does not jump to the bottom when staff are reading older messages. Histories
  and contact lists are paginated. Staff login and tenant ownership protect all
  history, polling, replies and media endpoints.
- Old messages are not automatically recoverable. Historical import would require
  a separate authorized export from the previous system.

### Runtime

`start.sh` runs migrations, then `scripts/serve_with_inbox.py` starts Gunicorn and
`python manage.py run_whatsapp_worker`. The worker uses PostgreSQL, not Redis;
it handles inbox replies and optional Meta-to-n8n forwarding. If either child
exits, the supervisor stops both so Render can restart the service. Other Huey
transactional jobs keep their existing worker requirements.

For local development run the Django server and:

```bash
python manage.py run_whatsapp_worker
# One pass for diagnostics:
python manage.py run_whatsapp_worker --once
```

Never run a local worker against production data as a test. Ensure the configured
n8n host and `graph.facebook.com` / Meta media destinations are reachable from the
production service. Live connectivity and actual delivery require client settings;
unit/browser tests use fake providers and send no real messages.
