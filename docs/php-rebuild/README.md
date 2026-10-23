# Annam Foods PHP migration

The PHP application now covers checkout, orders/fulfilment, manual bookings,
Razorpay verification/refunds, compact logo billing, WhatsApp inbox/queue/sync,
courier settings, published content/media compatibility and migration tools.
Code is in [`php-app`](../../php-app/README.md); architecture is documented in
[`php-app/ARCHITECTURE.md`](../../php-app/ARCHITECTURE.md).

This work is on **`php-rebuild`**. The live Django/Render site and production
Supabase database have not been replaced. Live provider acceptance and Hostinger
capability checks must pass before deployment; local tests do not certify them.

- [Download Hostinger package](annam-foods-hostinger.zip)
- [Download local review package](annam-php-preview.zip)
- [Compact logo bill](compact-bill.png)
- [Courier pincode table and toggle](courier-settings.png)
- [Order receipt](checkout-receipt.png)

The Hostinger package separates `annam-private/` from `public_html/`. Both ZIPs
exclude actual environment files, credentials, database exports, customer uploads,
sessions and logs. Supply the complete saved media backup and a test database
copy separately. Do not upload private application files into public_html.

| Area | Implementation and verification |
| --- | --- |
| Catalog, menus, delivery, pages/settings | PHP services, admin and storefront implemented |
| Checkout / receipt privacy | Server quote/review, exact coverage/minimums, idempotency and browser checks |
| Payments / refunds | Provider boundary, encryption, signatures/evidence, retries and callback deduplication; simulated tests |
| Billing | Immutable snapshots, locked numbering, credits, logo/address receipt and Print / Save PDF |
| WhatsApp / n8n | Signed/token-authenticated inbox sync, queued replies, receipts, attachment proxy and cron |
| Published design / photos | Existing configuration and asset routes retained; recoverable photos materialized in media |
| Migration/deployment | Read-only data fingerprints/readiness, scoped media ZIP and upload package |
| Hostinger / real providers | Requires actual account capability checks and sandbox/live acceptance |

Verification completed locally:

- **43 PHP behavioral tests** against a disposable PostgreSQL database; fixture
  records rolled back; fake provider calls only.
- Browser login, dated menus, checkout-to-payment-confirmation-to-bill, private
  guest receipt, courier-table saving, payment tabs, inbox/settings, media export,
  product creation and mobile navigation.
- A nine-item lunch bill exported as **one A4 page**, with the original logo.
- PHP syntax checks, runtime preflight, read-only baseline/compare and media ZIP
  inspection. Local baseline comparison reported no changed scoped tables.
- **546 Django tests passed**, plus Django system/schema checks.

External work remains: confirm `pdo_pgsql` and outbound TLS on the actual
Hostinger plan, restore/review real data and all uploaded photos, run real Razorpay
sandbox and Meta/n8n tests, configure cron and perform the HTTPS/domain cutover.
The deployment/rollback procedure is in the PHP README. No real payment, refund
or WhatsApp message was initiated by the local test runs.
