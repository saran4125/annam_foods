# PHP production-target parity review — 2 November 2026

Reference: Django `main` at `2a7b5e2`. Runtime target: PHP 8.2+ with Supabase/PostgreSQL.
The live Render application was not replaced. No real payment or message was sent.

| Behavior | PHP implementation | Evidence |
| --- | --- | --- |
| Dedicated Annam storefront/admin, published content, original logo | Application, Content, existing templates | Chromium storefront/admin/bill |
| Date menus, empty menus, Today/Tomorrow highlight, safe edits | Store, Delivery, Cart | Native revision/counter tests; browser date-menu save |
| Tomorrow preorders, opening days/time and cutoff | Delivery::slotOpen | Boundary tests; browser tomorrow order |
| Breakfast/Lunch/Snacks combined; Dinner separate | Cart, Delivery, StaffBooking | Exact Dinner message tests; browser combined order |
| Approved meal pincode/category coverage | Delivery::local/restriction | All required restriction messages tested |
| Same-pincode area choice, minimum excludes fee, one fee | Delivery, Checkout, Pricing | Shared-area/minimum tests; combined bill with one fee |
| Snacks local delivery versus outside-Chennai courier | Delivery::snacks | Outside-state/foreign and missing Chennai zone tests |
| Deferred courier disclosure/customer+team drafts | Courier, checkout/review/receipt/settings | Held-draft tests; provider execution defaults offline |
| Post-dispatch courier fee and separate receipt | Courier, CourierPayments | Immutable charge and independent receipt tests |
| Separate online courier payment | CourierPayments, callbacks/cron/receipt | Signature/amount/provider evidence, idempotence and test-mode isolation tests |
| Financial review/duplicate submission/private receipt | Checkout, Orders | Native tests and Chromium placement |
| Exact meal-group order tabs | Reports, orders view | Native grouping/filtering and browser |
| Product/category/date/time reports and CSV | Reports, reports view | SQL aggregate tests and Chromium report |
| Daily orders/sales/receipts/refunds/courier monitoring | Reports::sales | Tests distinguish test-mode and separate courier receipt |
| Category-family counts, item CRUD, stocked/hidden/empty views | ParityRoutes, Resources | Native family tests and Chromium category item management |
| Phone-first saved customer details, editable after filling | CustomerLookup, StaffBooking, lookup JS | Scoped local/+91 tests and Chromium autofill/edit |
| Reviewed catalog snapshot, stock, weight, private review notes | CatalogSync, Resources | Full reference-catalog dry run, apply and no-op re-run |
| Reviewed delivery CSV/locality names | import-meal-zones.php | 63 CSV rows plus approved 600041 split (64 areas), checked on isolated clone |
| Logo/address/one-fee compact invoice, immutable numbering | Billing, bill view, receipt CSS | Financial regression tests; Chromium paid combined-order bill |
| Razorpay verification, callback authentication, refunds | Payments, Razorpay | Existing mocked capture/failure/retry/refund suite |
| WhatsApp inbox, copies, receipts and replies | Messaging, MessagePayload, Worker | Existing mocked signature/account/sync/window/deduplication suite |
| Shared atomic login/lookup limits, no-store, scoped records | Operations, Security, Store | Throttle/tenant tests and unauthenticated HTTP boundary checks |
| Restricted media/private attachments and secrets | Media, Attachment, deployment rules | Traversal/executable/foreign-scope HTTP tests |
| Bounded processing, database timeouts, worker readiness | Worker, Database, cron, /readyz | Offline cron heartbeat execution, native worker tests |
| Encrypted DB/media/config/key backup and restore | Recovery, recovery CLI | Authentication/tamper test and empty-schema restoration, transactionally rolled back |
| Optional private offsite backup | offsite-backup.php | Implemented; real Supabase bucket/upload not configured or tested |
| Hostinger ZIP with private/public split and checksums | package-hostinger.php | Built locally; contains no DB, user media, private env or sessions |

Validation recorded for this change:

- 53 native PHP behavioral tests pass using rolled-back fixtures on a disposable PostgreSQL clone.
- Real Chromium: category item list, dated menus, combined tomorrow checkout, one fee,
  manual receipt, original-logo bill, saved-address autofill/edit, reports, mobile shop.
- HTTP checks: private paths, host validation, CSRF, cross-store asset and unauthenticated callbacks.
- Encrypted archive verified and tampering refused; schema and 315-product catalog
  restored inside a disposable transaction, then rolled back.
- Django reference PostgreSQL suite: 643 passed (one pre-existing deprecation warning).

## Release boundary

These checks establish local implementation behavior, not a production uptime or
traffic-capacity guarantee. Before PHP cutover, verify Hostinger `pdo_pgsql`, Supabase
TLS access, the complete actual media folder, private storage/cron, live-domain HTTPS,
real Razorpay sandbox flows, Meta/n8n templates/callbacks and offsite restore on staging.
Payments and messaging remain offline by default. The unconfirmed Mavadu price/pack
size and build-only catalog decisions remain private review notes. Past menus are
preserved rather than replaced with obsolete imported dates.
