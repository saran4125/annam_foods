# The n8n send workflow

Only needed for a tenant whose `wa_provider` is `n8n`. Most tenants should use
`meta_cloud` and skip this entirely.

The whole point is that this workflow contains **no logic**. The app has
already decided what to say, validated it against Meta's limits, and built the
exact body Meta expects. n8n forwards it and reports back.

If you ever find yourself adding an IF node here, something has gone wrong —
that decision belongs in the app, where it can be tested.

## Four nodes

```
Webhook (POST /webhook/wa-send)
   ↓
Validate auth header          (Code — one comparison)
   ↓
HTTP Request → Graph API      (forwards {{ $json.body.graph }} unchanged)
   ↓
Respond to Webhook            ({ "wamid": … })
```

## What the app POSTs

```json
{
  "tenant": "annam",
  "to": "919551079550",
  "purpose": "order_confirmed",
  "message_id": 4172,
  "payload": { "kind": "text", "body": "Your order is confirmed." },
  "graph": {
    "messaging_product": "whatsapp",
    "to": "919551079550",
    "type": "text",
    "text": { "body": "Your order is confirmed." }
  }
}
```

`graph` is ready to POST to Meta as-is. `payload` is there only if you want to
build the request differently — for a client on a non-Meta provider, for
instance.

Header: `Authorization: Bearer <TenantSecrets.n8n_auth_token>`.

## Node settings

**Webhook** — POST, path `wa-send`, response mode "Using Respond to Webhook".

**Validate auth** (Code):
```javascript
const expected = 'Bearer ' + $env.SEERKITCHEN_TOKEN;
if ($input.first().json.headers.authorization !== expected) {
  throw new Error('Unauthorized');
}
return $input.all();
```
Without this, anyone who finds the URL can send messages as your client.

**HTTP Request**:
- POST `https://graph.facebook.com/v21.0/<PHONE_NUMBER_ID>/messages`
- Header `Authorization: Bearer <WABA token>`
- Body: JSON, expression `{{ $('Webhook').item.json.body.graph }}`
- **Leave `continueOnFail` OFF.** A failure must reach the app as a non-2xx so
  the message is retried. Swallowing it here is exactly the silent failure this
  architecture exists to avoid.

**Respond to Webhook**:
```javascript
{ "wamid": {{ $json.messages[0].id }} }
```
Returning the id lets the app record it. A bare 200 also counts as sent.

## What the app does with the reply

| n8n returns | App does |
|---|---|
| 2xx | marks the message sent, records `wamid` if present |
| 4xx | permanent — the workflow rejected it, retrying the same body won't help |
| 5xx or timeout | transient — retried with backoff, up to 5 attempts |

A dead n8n therefore delays a message; it never loses one. The
`OutboundMessage` row stays `failed` with the error on it and is picked up by
the next worker run.

## Configure the tenant

In the super admin, on TenantSecrets:

- **wa_provider**: `n8n`
- **n8n_send_url**: `https://automation.seerbusiness.com/webhook/wa-send`
- **n8n auth token**: the shared secret, matching `SEERKITCHEN_TOKEN` in n8n

Switching back to `meta_cloud` later is that same dropdown. Nothing else in the
system changes.
