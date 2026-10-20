# Connect the existing n8n automation to the WhatsApp inbox

Open `/manage/whatsapp/settings/`. Only two settings are needed to display
customer messages and n8n replies:

1. **Meta phone number ID:** use the numeric phone ID already used by n8n.
2. **n8n inbox sync token:** choose a random secret of at least 24 characters.
   Store the same token in n8n Header Auth with header `Authorization` and value
   `Bearer <token>`. A token is required the first time; a blank field after that
   keeps the existing encrypted value. Saved secrets are never shown in the form.

Keep the Meta callback pointing to your existing n8n workflow. No new Meta
callback, app secret, access token or forwarding URL is needed for message sync.
Existing send-workflow and advanced connection settings are preserved when this
form is saved. The form controls message mirroring, not sending staff replies.
Do not place secret values in Git, chat, webhook URLs or workflow exports.

## 2. Copy incoming messages from n8n

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
`contacts`, `messages`, `statuses` and the original timestamps. The phone number ID must match the saved setting. Incoming status callbacks use the same structure
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


## Result

Both incoming and outgoing copies are required to show the full conversation at
`/manage/whatsapp/`. Meta delivery callbacks alone do not include outgoing reply
text. Include status callbacks in the incoming copy to display delivered/read
states. The endpoint stores new messages and deduplicates repeated message IDs.
It does not send a new WhatsApp reply or forward the event back to n8n.

Keep each sync node separate from the actual send node: retrying a copy must not
resend the WhatsApp message. Old chat history is not imported automatically.
Image/audio/document previews require an existing server-side media connection;
recording the messages does not require one. Unconnected previews are clearly
marked in the inbox.

A **Create order** link opens WhatsApp billing with the customer name/phone
prefilled. Chat messages are order requests; staff still select catalog items and
confirm actual payment before billing. The inbox is protected by the existing
staff login and each kitchen's tenant access rules.

`start.sh` supervises Gunicorn and the database-backed inbox worker. Migrations
run before startup. Live Meta/n8n credentials and workflow changes must be made
in their respective settings; a Git deployment does not connect them automatically.
