# Cart layout update — 19 November 2026

Includes the Python reference cart layout: compact dish rows, +/- quantities,
meal/date context, pincode panel, delivery notes, separate totals and full-width
checkout action. Auto pincode validation and saved meal delivery after quantity
updates are retained. Includes the category, stock and billing changes below.
Apply this code-only update to the existing Hostinger installation; preserve
the database, private configuration, installation.json and uploaded media.
The Render preview is intentionally not redeployed because its temporary
database would reset.

---

# Hostinger category and stock update — 19 November 2026

This code update simplifies categories to one unfiltered item list, automatically
uses a dish photo when a category has no artwork, removes the category photo
upload field, and makes repeated stock submissions keep the requested state.
It includes all earlier billing and management changes listed below.

For an existing Hostinger installation, back up then merge `annam-private/`
and `public_html/assets/` into the matching folders. Preserve the existing
SQLite database, installation.json, .env, media and other runtime files.
No database/owner configuration replacement or stock reset is required.
Clear PHP OPcache/restart PHP and refresh management pages after uploading.
This is an update package; it does not include a first-install database or media.

The free Render preview uses temporary /tmp SQLite. Redeploying it recreates its
data; this code change cannot make free Render storage persistent. This release
is prepared on a separate Hostinger branch to avoid triggering that redeploy.
Hostinger keeps the database under annam-private/storage on persistent hosting.

Validation: 72 PHP behavior checks, 546 PostgreSQL reference tests, and local
Chromium desktop/mobile category/photo/repeated-stock/form checks passed.

---

# Payment and customer invoice update

Python main: customer invoice links now work for manual paid orders too, with
private PDF downloads, receipt refresh and a same-browser recent-order link.

PHP: live-only normal checkout; separate test/manual switch; unpaid online status
guards; verified capture confirmation; immediate website invoices; actual PDF
attachments and automatic refresh/download with manual fallback. Test captures
create TEST receipts without real invoice numbers. Receipt and checkout layouts,
orders filters/status badges, resource tables and short-screen header behavior
are updated.

The two ZIPs are code-only. Neither replaces any database, customer/order data,
`.env`, installation configuration, setup credentials, uploaded media or sessions.

For a repository layout, merge `php-app/` source into the existing application.
For split hosting, merge `annam-private/` and `public_html/assets/` from the update
ZIP into the matching directories. Keep the existing entry point, private config,
installation state, database and media. Include `resources/vendor/tcpdf` in full,
including `.z` fonts and licenses. Restart PHP or clear OPcache after upload.

Set the temporary test switch off for real customers. Configure enabled LIVE
Razorpay and `PAYMENTS_ENABLED=1`; checkout is unavailable until both are ready.
Existing unpaid orders remain retryable; do not ask a paid customer to pay again.

Git push does not deploy PHP to EC2. Actual Razorpay charges and live provider
credentials were not verified. Use staging before separately deploying the code.

Verification on disposable databases: Python main 668 PostgreSQL tests; PHP
branch 546 PostgreSQL tests; 58 PHP behavioral checks; PHP lint; SQLite contract,
concurrent stock/order/invoice allocation and encrypted recovery checks. Browser
checks covered management/mobile layouts, 1280×720 checkout, manual confirmation
polling, one automatic invoice download, same-browser recent-order navigation,
foreign-browser denial, mocked signed capture, bad signatures, TEST PDF download
and absence of financial invoices for test capture. PDF text was extracted and
checked. These checks used simulated provider evidence, never real charges.

Recent-order follow-up: the empty cart now displays the last order's items,
quantities, total, fulfilment/payment status and receipt link. A separate signed
HttpOnly guest cookie retains access for 30 days across browser restarts and PHP
session cleanup, without extending staff logins. Clearing cookies or switching
browsers removes guest access. Verified using a real Chromium close/reopen with
the PHP session cookie removed; another browser remained denied. PHP behavioral
suite now includes 59 checks.

## Complete PHP UI package — 18 November 2026

Includes the management-panel login, sidebar, dashboard, catalog/menu editor,
orders and order details, reports, resource lists and settings UI, together with
all PHP payment/receipt/PDF and persistent recent-order work above. The latest
meal-pincode auto-check and navigation-blanking fix are now ported from Python.
Checkout keeps Review & place order and the final confirmation/payment action
visible on short desktop and mobile screens. Checked pincodes prefill checkout.

The source ZIP is the complete PHP application code. The update ZIP supplies
private code under annam-private/ and public assets under public_html/assets/.
Neither archive contains a live database, .env, installation state, account/order
records, uploaded media, fixture routers or credentials. Keep all those existing
installation files when applying the update. This is not an EC2 deployment.

Pending policy, not included: removing the courier-enabled/configuration blocker
for Tamil Nadu shop products was analyzed but has not yet been implemented.
Normal online checkout still requires configured live Razorpay; temporary test
checkout stays separate. Do not interpret this package as live provider acceptance.

18 November package validation: 546 PostgreSQL regression tests, 59 PHP behavior
checks and PHP lint passed. Management UI browser checks covered login, sidebar,
dashboard, catalog, menu editor, orders, reports, settings, desktop/mobile layout
and navigation. New checkout browser checks covered automatic/invalid meal
pincodes, manual retry without document navigation, saved pincode prefill, fixed
review/place actions and disposable desktop/mobile orders. No live payment or
production order was used for these package checks.

## Health Mix homepage artwork fix — 18 November 2026

The Health Mix section now restores its reviewed image when the imported section
has no artwork. Published owner artwork and existing local product photos take
precedence. The fallback photo is shipped as public_html/assets/health-mix.jpg
in the update ZIP (php-app/public/assets/health-mix.jpg in the source ZIP), so it
works without replacing or restoring any uploaded-media folder or database.
The 17-ingredient heading and responsive image dimensions match Python. A generic
spotlight without a suitable image uses one column instead of a blank grid area.
Both archives retain all prior management-panel, payment, invoice and checkout
updates. Apply the private code and public assets together; clear PHP OPcache.

## Staff booking category selection fix — 18 November 2026

The duplicate category selection is removed for PHP booking items assigned to a
single meal (and shop items, which already belong to Snacks). Their existing
category is carried automatically; multi-meal/unknown items retain an explicit
choice so no fulfilment category is guessed. Server assignment checks remain.
Python's searchable item picker now records the chosen meal directly, including
multi-meal choices, and no longer renders the second required Food category field.
Validation: Python 671 tests; PHP branch 546 tests; 60 PHP checks; desktop/mobile
Python picker and PHP booking browser checks, including successful test bookings.
Both ZIPs retain the Health Mix artwork and all prior management UI fixes.

## Dedicated billing portal and payment not received — 18 November 2026

PHP no longer redirects the billing portal into general management. It now has
Python-style dedicated overview/source lists, searchable meal picker and booking,
saved customer lookup, shared billing settings, payment/order detail, provider
status/refund controls, bill printing and real PDF downloads. Search, payment
filters, pagination and desktop/mobile layouts are covered by browser checks.
The portal reuses the existing tenant-scoped services and staff accounts.

Manual and WhatsApp bookings can select Payment not received / collect on
delivery or record that choice on an unpaid order. Delivery, including Delivered,
does not mark payment received. After collection, staff explicitly confirm the
full amount and issue exactly one immutable bill. Paid/refunded/invoiced orders
cannot be reverted to unpaid; online website payments cannot use this action.

Read BILLING-PORTAL.md inside either ZIP for the route/workflow parity matrix.
The Python change passed 673 PostgreSQL tests; the PHP branch passed 546
PostgreSQL reference tests and 62 PHP behavioral checks. Desktop/mobile browser
checks completed both portals' booking -> collect later -> delivered/unpaid ->
confirm actual collection -> bill flow, including PDF, CSRF and filtering checks.
No production order, payment or database record was used for these checks.
All previous management UI, Health Mix image, checkout, receipts and recent-order
updates remain included. The separate shop/courier policy change remains pending.

## Website billing collection visibility correction — 18 November 2026

The screenshot reported a Website order, which the earlier source-based check
excluded. Existing website orders arranged for manual payment now have Payment
not received / collect on delivery too. Actual online modes/provider intents
cannot be manually collected or settled, even if the provider intent is missing;
those orders instead show a clear read-only Payment not received status.
Normal checkout's payment choices and configuration are unchanged.

Validation: Python full suite 675 passed plus 17 billing-focused checks; PHP
reference suite 546 passed and 63 PHP business checks passed. Browser checks
verified manual-payment website collection visibility and online protection on
both portals at desktop/mobile sizes. Both ZIPs retain all previous changes.
