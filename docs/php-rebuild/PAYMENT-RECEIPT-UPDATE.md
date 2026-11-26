# Equal display-order numbers — 26 November 2026

For dishes/products with the same numeric Display order, the most recently saved
number wins. Re-saving rank 1 moves that dish ahead of other rank-1 dishes. Lower
numbers still precede higher numbers. A dedicated sort_priority value is changed
only by an explicit Display order submission, never by stock/order updates.
Existing records retain a stable fallback until their display order is saved.
The additive schema upgrade supports both SQLite and PostgreSQL; Python main
has the matching Django migration, ordering and form behavior.

---

# Display order consistency — 26 November 2026

Saved item order now takes priority over category position. Equal ranks use
name and unique ID so pagination stays stable. Category positions respect their
saved order, including the four starter categories. Partial edits preserve rank.
Home favourites stay grouped first, with numeric order inside each group rather
than photo priority. Python also includes favourites beyond the first 60 items
and includes all shop categories in the default Shop shelf.

Validation: PHP SQLite and PostgreSQL native suites (91 checks); Python full
PostgreSQL suite; local browser checks of both shop sort modes and Python's dated
Breakfast edit followed by admin/customer menu reload. The reported Breakfast
save failure could not be reproduced locally; its complete flow is now covered.

---

# COD invoice address and wording — 26 November 2026

Issued invoices now show saved address lines even for collection bookings.
Unsettled COD documents say Cash on delivery and retain their amount due;
manual/online unpaid and paid/refunded states keep their own labels. Financial
snapshots, numbers and payment flags are unchanged. Browser export fetches only
the authorized receipt markup into an isolated print frame, so it also works
with Django's unchanged frame protections. Native PDF includes the same address
and COD wording. Matching fixes and rebuilt features are ported to Python main.

---

# Repeat checkout addresses and delivery refresh — 25 November 2026

The same signed guest browser can reuse its latest placed-order address for
an exact Indian pincode. Other pincodes need their own address. Only this
browser's tenant-scoped orders are searched; there is no public lookup by
phone or pincode. The signed guest cookie lasts 30 days. Address fields remain
editable, and saved area IDs/payment methods are never restored automatically.

Changing pincode clears address fields, area choice, delivery estimate and
continuation state immediately. A fresh scoped delivery check enables review
only when eligible; multiple areas require a new selection. Stale responses
cannot replace newer results. Review and placement independently revalidate
coverage, area and totals; a charge change after review requires another review.

Verified an actual local repeat order, address restoration after session loss,
browser/tenant isolation, changed pincode and area charges, unsupported pincode,
mobile layout and final charge-change rejection. PHP behavioral checks: 89.

Also added the requested left/right arrows to Shop category tabs. Arrows scroll
the category strip and disable at its edges; touch scrolling remains available.

---

# Fresh preview startup fix — 25 November 2026

Removed the retired Snacks slot creation from the Render fresh-catalog seed.
The previous deployment rejected that seed through the new meal-time validator
before Apache could start. Existing databases are still preserved on startup. Health checks include the
public Render commit SHA when available, so deployment success can be verified
without confusing an older healthy deployment with the new release.

---

# Remove Snacks meal time — 25 November 2026

Removed the legacy Snacks slot from meal-time management and active meal
selectors, and removed Snacks from delivery-area meal checkboxes. New Snacks
meal times are rejected. Existing slot rows remain for historical order and
schedule references; shop snack products and historical invoices are unchanged.

---

# Clear catalog pagination — 25 November 2026

Dishes & products and category item lists now show Page X of Y, an orange
current-page highlight, Previous/Next arrow links, and ellipses between skipped
pages. Boundary arrows are disabled, and navigation preserves active filters.
Controls wrap on small screens and identify the current page for screen readers.

---

# Exact main-branch receipt layout — 25 November 2026

Copied `static/css/receipt.css` unchanged from Python main commit
`87239dd44df9d3b64c50e22895e376b8c164fcdf`, and translated
`templates/billing/_invoice_body.html` directly into PHP. The presentation
adapter preserves frozen invoice values and matches Python address, payment,
discount, tax, delivery-note and two-decimal amount formatting.

Normal browser Download PDF links now export the authorized invoice's actual
DOM using the copied print rules. Print / Save PDF uses the browser's print
renderer. The browser download is an image-based A4 PDF; print retains text.
The existing authenticated server PDF remains the no-JavaScript/error fallback
and uses its separate TCPDF renderer. No order, payment, numbering or invoice
snapshot data is rewritten by this presentation update.

Validated identical receipt pixels against the main Django template at 900px,
390px and A4 print widths, plus an authenticated one-page PDF download. Full
PostgreSQL reference suite: 546 passed. PHP behavioral checks: 88 passed.

The export dependency is locally bundled html2pdf.js 0.14.0 (MIT), from the
npm package of that exact version; license is retained in
`php-app/resources/vendor/html2pdf/LICENSE`. No invoice is sent to an external
PDF service.

---

# Four-category item library — 25 November 2026

Categories starts with Breakfast, Lunch, Dinner and Shop, with custom categories
still available under Custom categories. Main categories opens with the four
defaults only. Missing defaults are added once; existing categories and data
are kept. Categories shows the whole item library; Dishes & products manages
meal/date availability and stock.

Create a meal dish once and choose any combination of Breakfast, Lunch and
Dinner. The same dish appears in those libraries and daily pickers. Shop opens
the Shop products form. Master assignment does not publish a menu or rewrite
saved schedules. Billing uses the same meal assignments. Existing stock,
photos, product tags, orders and bill snapshots are preserved.

Validation: 87 PHP checks on SQLite and PostgreSQL, 546 reference tests, and
browser checks for the four defaults, a shared three-meal item, billing groups,
independent Breakfast/Lunch daily selections and desktop/mobile forms.

Merge code while keeping the existing database, configuration and media.
See MANAGEMENT-PARITY.md for the client workflow.

---

# Shop control spacing — 25 November 2026

Category tabs now have a 24px gap above the search/sort controls, with 32px
between those controls and the product grid. Mobile uses 18px and 24px gaps.
The change is scoped to shop/category pages; category scrolling, searching,
sorting and product ordering remain unchanged.

---

# Confirmation page parity refinements — 25 November 2026

Confirmation now uses Awaiting payment for pending orders, the reference
1.55:1 columns and spacing, compact payment copy and paired View/Download
actions. Checkout navigation matches Home / Daily menu / Shop; About us remains
available on the other storefront pages. Custom payment instructions appear
once. Payment-awaiting prompts disappear when live receipt updates report paid,
refunded or cancelled state.

Unissued orders have View order summary and an orange Download order summary
PDF action. The preview is an inline PDF with the same browser ownership checks
as the download. When an invoice is issued, polling swaps the summary actions
for View invoice / Download invoice PDF. No invoice is allocated by viewing.
Desktop/mobile checks cover both action states, payment updates, column widths,
summary PDF preview and denial from another browser.

---

# Branded recovery pages — 25 November 2026

Session-expired and other error pages now use the website logo, warm cream
background, display typography, rounded card and orange primary action. Checkout
session errors offer Return to checkout and View cart via safe GET links, with
a reminder to check an existing recent order before placing another one.
Management/billing session errors return to their own login. Not-found pages
link back to the menu. CSRF checks, status codes and escaped messages remain.

The fallback does not depend on a working database: its logo is embedded from
the bundled brand file. Desktop/mobile checks cover the 403 session response,
404 response, loaded logo, recovery links and horizontal overflow.

---

# Three checkout pages matched to Python — 25 November 2026

Delivery details now use the same field order, full-width street/locality,
helper card and estimated-total panel as the reference. Review uses the same
item lines, delivery-address section, final-total card and fixed Place order
action. Edit delivery details restores this browser's unexpired review values.
Order received shares the item/address layout and total card, with truthful
payment state, existing receipt actions and a Contact the kitchen link.

Shared delivery-area selection, server-side repricing, payment verification,
invoice availability and recent-order ownership remain in effect. Unissued
orders offer an order summary; the design does not mark pending orders paid.
Desktop/mobile browser checks covered details, review, edit/back, place order,
confirmation and recent-order access without horizontal overflow.

---

# Recent order in the empty cart — 25 November 2026

The PHP empty cart shows Your recent order with its order number, order and
payment status, items, total and receipt link, matching the Python storefront.
The lookup supports both signed PHP guest identity and a verified migrated
Django browser session, scoped to the current store. Other browsers cannot
view the order. The signed guest cookie also restores access after PHP session
expiry; no customer login is required.

Orders from the separate Python deployment do not automatically transfer to
PHP. The order must exist in this site's database and belong to the current
browser. Erasing temporary preview storage also removes its order history.

---

# Downloaded PDF receipt design — 25 November 2026

Server-generated invoice and order-summary PDFs now share the receipt design
from the Python bill: rounded outer border, compact seller and customer details,
subtle separators, item detail lines, a highlighted total and centred footer.
The Download PDF action uses this design without requiring browser print.

Unissued orders remain labelled Order summary / not a tax invoice. Issued bills
use immutable invoice snapshots and the current paid, unpaid or refunded state;
this layout change does not issue bills, allocate numbers or mark orders paid.
Long orders continue onto framed pages. Simulated-payment receipts remain
clearly marked TEST and do not become invoices.

---

# Category deletion — 25 November 2026

Categories now show a Delete icon beside Edit. The confirmation screen explains
that products are kept without a category and child categories become separate
categories. Cancel keeps everything unchanged. Only a confirmed, CSRF-protected
POST deletes the category; all updates are scoped to the signed-in store.
Products, inventory balances, saved daily menus and order/bill snapshots remain.

---

# Simpler dish and shop forms — 25 November 2026

Removed Verified pack size and Internal review notes from meal and shop
add/edit forms. Existing stored values are preserved when saving other details.
This is a code update; keep the existing database, configuration and media.

---

# Compact form toggles — 25 November 2026

Switch, label and On/Off state now stay together in a compact control across
management and billing forms. Long labels wrap within the available space;
controls retain a minimum 46px height. Daily-menu dish cards keep their name
and price columns. Checkbox submission and stored settings are unchanged.

Upload the code-only Hostinger update while preserving the existing database,
.env, installation.json and uploaded media. Asset URLs include content hashes,
so browsers request the new CSS after upload. No live deployment is included.

Checked 29 visible switches at both desktop and mobile widths across resource,
store, checkout, payment, report and billing forms, including click behaviour
and horizontal overflow. All 546 PostgreSQL reference tests passed.

---

# Optional quantity tracking — 23 November 2026

Quantity tracking is off by default. Open the Quantity control for any dish or
shop item, turn it on, and set the available quantity or add stock. Shop stock
is shared; meals use the selected meal/date. Manual bills without a delivery
date use today. Saved orders reserve once, unpaid orders included. Payment and
invoice actions do not deduct again; cancellations restore once. At zero,
ordering stops until stock is added.

Merge the code-only Hostinger update. Inventory tables are added automatically;
keep the existing SQLite database, installation.json, .env and uploaded media.
Do not replace the database or rerun demo seeding. No live deployment is included.

Validation: 81 PHP behavioural checks on SQLite and PostgreSQL, concurrent
last-unit/retry/invoice checks,
desktop/mobile quantity-editor checks and all 546 PostgreSQL reference tests.
See MANAGEMENT-PARITY.md for the flow.

---

# Checkout areas sharing a pincode — 23 November 2026

One matching delivery area is automatic. When a pincode covers multiple active
areas serving the cart's meals, checkout asks the customer to choose and shows
each charge. The chosen fee and estimated total update automatically. Changing
the pincode clears the previous area. Final review validates the selection and
prices again on the server, including with JavaScript disabled.

In Delivery areas, create each area as a separate entry with the same pincode
and its own name, charge, minimum and supported meals. No schema migration or
replacement database is required. Preserve database, configuration and media
when merging this Hostinger code update.

75 PHP checks and 546 reference tests passed, plus desktop/mobile and no-JS
browser acceptance of the two different fees and final review totals.

---

# Persistent stock update — 23 November 2026

The latest saved product stock value is preserved when editing other product
details. Explicit stock changes remain supported; no product is forced to a
hardcoded default.

For Hostinger, merge this code-only update into the existing installation. Keep
annam-private/storage/annam.sqlite, installation.json, .env and uploaded media.
Do not upload a replacement demo database or rerun catalog seeding.

Optional Render persistence support now requires a real mounted /var/data disk
and PREVIEW_DATA_ROOT=/var/data/annam-php-preview. Existing databases are preserved
and missing initialized databases refuse demo reseeding. The FREE preview still
has ephemeral storage; this release does not purchase or attach a disk. Back up
and restore the current database before moving it. Hostinger remains the chosen
permanent destination.

Verified: latest true/false states survived replacement of a disposable container
using the same persistent volume, later updates survived restart, and missing
databases were not reseeded. 74 PHP checks and 546 reference tests passed.

---

# Checkout and document layout polish — 20 November 2026

Aligned checkout inputs, full-width payment selector, tablet/mobile layout and
non-overlapping floating controls. Pending-order PDFs now use the branded bill
layout with logo, customer/delivery details, items, totals, amount in words and
seller footer; they remain clearly marked pending and not a tax invoice.
Legacy and transparent bundled logos now embed correctly in PDF downloads even
without optional image extensions. Existing invoice/payment records are preserved.
Apply the code-only update while keeping database, configuration and media.

---

# Customer invoice section — 20 November 2026

Confirmation pages now always show an Invoice & receipt section. Pending orders
can download a clearly labelled non-invoice order summary. Staff-issued unpaid
bills are available as invoice PDF downloads too. Payment remains pending until
collection/capture is confirmed. No invoice is invented for test/unpaid orders.
Preserve database, private configuration and uploaded media during updates.

---

# Checkout inline validation — 20 November 2026

Invalid phone numbers and delivery details now keep the customer on checkout
with their entered details and a visible error. Correcting the error allows
review without refilling the form. Includes mobile-number format guidance.
Preserve existing database/configuration/media when applying this code update.

---

# Checkout delivery-field update — 20 November 2026

Removes the delivery-area dropdown from customer checkout. Pincode-based delivery
validation remains, with any same-pincode area selected in the cart retained.
Preserve the existing database, installation configuration and media on upload.

---

# Quantity buttons and preview checkout — 20 November 2026

Fixes invisible +/- symbols by restoring the reference stepper contrast. Render
preview checkout now explicitly uses labelled TEST / temporary manual payment,
so its review action can be tested while all payment/message providers stay off.
The preview flag is configured only by the guarded Render initializer; uploading
this Hostinger update does not enable temporary payments on a production store.
For real online orders, configure the enabled LIVE payment connection as usual.
Preserve existing Hostinger database, installation configuration and media.

---

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
