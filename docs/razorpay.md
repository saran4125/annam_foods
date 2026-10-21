# Razorpay setup and verification

Each kitchen connects its own Razorpay account at **Admin → Razorpay payments**.
Test/live credentials are encrypted in separate tenant-owned connections. Only
an active kitchen owner or platform superuser can save keys or request refunds.
The Key ID is public by design; API and webhook secrets are never rendered back.
Existing credentials in TenantSecrets are copied as **disabled** connections at
migration time, so enabling an untested account is always an explicit action.

## First sandbox check

1. Open Test mode in the admin settings and enter the Razorpay test Key ID and
   Key Secret. Choose a separate webhook secret of at least 16 characters.
2. Enable Razorpay and save. The app makes a read-only API request to verify the
   credentials; saving settings never creates a charge.
3. In Razorpay's Test dashboard, add the exact URL displayed in settings:
   `/platform/webhooks/<kitchen-slug>/razorpay/test/`. The URL must be publicly
   reachable over HTTPS. Use the same webhook secret and subscribe to:
   `payment.captured`, `payment.failed`, `order.paid`, `refund.created`,
   `refund.processed`, `refund.failed`.
4. Configure automatic payment capture in Razorpay. Authorisation alone never
   marks an order paid in this platform.
5. Order meals with a covered delivery pincode. Select online payment, review
   the test banner and total, place the order and open Razorpay Checkout. Use
   Razorpay's current sandbox payment details from its documentation.
6. Verify success, failed/cancelled attempts, retrying the same order, duplicate
   callbacks, closing the browser before returning, and a full test refund.
   Confirm incoming webhooks appear in Razorpay's delivery history.
7. Test payments are clearly labelled, do not move real funds and cannot issue
   real numbered bills. Do not fulfil them as paid production orders.

The integration is covered by simulated provider/API and browser tests. A real
sandbox transaction still needs the kitchen's API keys, public deployment and
webhook configuration; simulated tests are not live gateway verification.

## Going live

Complete Razorpay activation/KYC and the kitchen's billing identity, FSSAI/GST
and tax/rounding settings. Save live keys and a separate live webhook secret in
Live mode, register the displayed `/razorpay/live/` URL in the Live dashboard,
and explicitly confirm acceptance of real payments before enabling. Only one
mode is offered to new customers at once. Existing orders retain their chosen
mode/connection when a mode switch occurs. Manual payment remains a separate
checkout choice while the kitchen's manual-payments feature is enabled.

## Verification, billing and refunds

- Provider orders use the stored Decimal order total converted to integer paise.
  A signed review binds payment mode/account as well as quantities, prices,
  delivery coverage, fees and tax settings. Changed reviews are rejected.
- Browser callbacks use HMAC-SHA256 over the **stored** provider order reference
  and supplied payment reference. The server then fetches the payment and checks
  order reference, exact amount, INR currency, captured flag and status.
- Webhooks use HMAC-SHA256 over the unmodified body with the selected kitchen's
  mode-specific webhook secret. Event IDs are deduplicated, provider state is
  fetched independently and payment transitions are serialized under row locks.
  Paid/refunded orders cannot be downgraded by delayed failure events.
- Captured live payments issue one bill when billing settings are complete.
  Billing errors never undo a verified payment; the owner sees a billing notice
  and can generate the bill after fixing settings. Customer bill viewing/printing
  is private to the purchasing browser session, just like its order receipt.
- Only owners may explicitly request a **full** refund. Pending/unknown outcomes
  are not submitted as a new refund. Provider idempotency keys, recorded request
  UUIDs and provider lookups support reconciliation after timeouts. A refund is
  marked complete only when fetched refund records say `processed`; a payment's
  refund amount alone is insufficient. Processed full refunds produce one credit
  note when a real bill exists. Partial refunds performed in Razorpay are shown
  for review; the app does not blindly issue another full refund.
- If provider-order creation times out, retry resolves the recorded receipt
  instead of creating another provider order. An unresolved outcome remains
  pending reconciliation. API keys cannot be replaced while open provider orders
  still need them. Test/live switching retains the other connection's credentials.

## Operations

Customers can use **Check payment status** on their private receipt. Owners can
refresh Razorpay/refund status from the order. Failed verification/webhook fetches
leave payment state unchanged and return a retryable error.

A bounded backstop command is available for an existing scheduler:

```sh
python manage.py reconcile_razorpay
```

Schedule every 15 minutes if a worker/cron is deployed. It reads pending provider
state; it never requests a new charge or refund. Webhooks and browser verification
operate independently of this scheduler. Unknown refunds may need a check in
Razorpay Dashboard if provider results remain unavailable. Never retry an unknown
financial outcome by manually creating another refund.

Automatic WhatsApp bill delivery, online partial-refund controls, and changes to
Annam's production domain are outside this integration. Existing n8n automation
continues unchanged.
