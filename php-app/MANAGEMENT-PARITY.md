# Management comparison — 19 November 2026

Reference: Python `annam-foods-9j2m.onrender.com`. Target: PHP
`annam-foods-php-preview.onrender.com`, branch `php-rebuild`.
The authenticated live reference and PHP preview were inspected read-only,
including all 15 sidebar destinations and their add/edit form structures.
Mutating acceptance tests use a disposable local PHP preview, never the Python
store or live customer/provider data. Credentials and customer data are not
included in this report or the repository.

| Tab | Comparison / corrections |
| --- | --- |
| Dashboard | Shared overview/cards/menu layout; reviewed preview catalog and dated menus restored. |
| Orders | Python-style meal counts, combined-order row, search/status toolbar, status/total column order, empty state and conditional pagination. Individual orders now use the items/customer/payment cards, status action buttons and history timeline. `all` no longer filters out orders. |
| Order reports & sales | Four headline figures, expandable receipt totals, refresh control, full styled date/meal/product/date filters, cancelled-order switch, six-column quantities table and CSV. Invalid report ranges remain in the form. |
| WhatsApp inbox | Shared two-pane inbox and disconnected state; search, unread totals, contact/message pagination, message history, periodic refresh, draft-preserving polling, read action and billing handoff. Offline reply controls stay disabled. |
| Dishes & products | Meal/date lists and day switches, corrected column alignment, weekly meal/time controls, inline validation. Reviewed 10/7/7 breakfast/lunch/dinner menus seed only fresh previews. |
| Categories | Product/visibility labels, category-item links and forms share admin styling. Empty categories remain under their own tab. |
| Meal times | Add/edit actions, cutoff and delivery columns, active switch and styled time inputs. |
| Offer banners | Add/edit/photo/link/visibility controls and management table layout. |
| Pages | Title, URL, menu flag, publication state and add/edit forms. |
| Razorpay payments | Test/live account controls, styled credential form and explicit live-payment acknowledgement. No live provider request made during this audit. |
| Checkout settings | Delivery sections, meal holidays, payment instructions and styled switches/fields. Existing business policy is preserved. |
| Delivery areas | Area/pincode/fee/minimum/delivering table and add/edit meal-coverage controls. |
| Billing portal | Overview, source lists, line picker, manual/COD order, delivery and invoice workflow checked. |
| Billing settings | Python-style business/tax form and switches; numbering format/timing preserved as hidden existing settings. Issued bills remain immutable. |
| Store settings | Store/look/hero/ordering sections, photo chooser, announcements and preview link. Additional PHP payment options remain under an advanced disclosure. |

The common form correction also applies to all resource add/edit pages. Desktop
and mobile checks cover every sidebar destination and additional forms. Weekly
schedule changes preserve dated menus and existing reservation counters and
reject another store's dish or meal time. Real Razorpay and WhatsApp delivery
remain separate integration acceptance; the preview deliberately disables them.

## Data differences

The preview is not a production database clone. Live orders, customer records,
receipts, conversations and owner changes made after the committed public
snapshots are not copied or invented. Empty order counts can therefore be
correct even when the interface matches. Fresh preview instances apply the
committed reviewed catalog and menus at their original dates and then carry
forward the latest saved meal. Existing databases are not reseeded; later staff
changes are preserved for the life of that temporary instance. A new Render
instance still resets ephemeral SQLite data.

## Validation

- 50 desktop/mobile management destination and form checks, with no document-width overflow.
- Local create/edit checks for categories, banners, pages, delivery areas and meal times; weekly meal assignment and invalid form handling.
- Store/checkout/billing settings saves; report filters, cancellation toggle, CSV and invalid date/range handling.
- Inbox 30-contact/50-message pagination, search, older-page polling pause, fresh-message polling, mark-read and prefilled billing handoff; offline sending remains disabled.
- Desktop/mobile manual/COD booking through delivery, confirmed collection, immutable invoice and PDF download.
- 72 PHP behavioral checks and 546 PostgreSQL reference tests pass.

## Simple menu reactivation

Hidden and out-of-stock meal dishes stay selectable in Choose dishes. Their
labels explain the current state and that selecting then saving enables the
product and marks it in stock across its menus. Only selected recovery candidates
change; cancelling does nothing. Unchecking removes the dish from this menu
without hiding it globally. Portion limits, sold counts and price overrides stay
intact. Historical dates, tenant scope and menu revision conflicts remain guarded.
The switches and Save action also work without JavaScript.

Category product counts include both scheduled meals and shop products, using
the same enabled/in-stock filters as their linked item lists. The label no longer
claims a dish is on the website regardless of daily menus or category visibility.
Category visibility remains independent of each product’s stock and sale status.

## Category simplicity and preview storage

Category names and the single item-count link now open the same unfiltered list.
Stock/on-sale counts are plain text; there is no second filtered destination.
Missing category images use a scoped dish photo (including active descendants),
preserving existing artwork. Category editing no longer asks for image uploads.
Stock POSTs submit an explicit desired state so retrying cannot reverse it.

The Render free preview uses /tmp SQLite and loses edits whenever its container
is replaced, including redeploys. These UI fixes cannot make ephemeral storage
persistent. Keep the existing preview running while choosing durable hosting;
the Hostinger package already stores its SQLite file outside the public folder
on the hosting account. Preserve the current database/config/media when updating.
Do not overwrite a live database with the reviewed demo seed.

## Customer cart reference layout

The cart now uses the Python reference cart/context/line/pincode/totals classes,
with compact server-priced +/- controls, vegetarian markers, a meal/date label,
fresh-order and add-more links. The right side separates pincode, delivery notes,
subtotal/delivery/total and a full-width continue action. Area selection appears
only when the entered pincode has multiple areas. Automatic pincode checking and
normal POST fallback remain; meal checkout is unavailable until delivery validates.
Saved meal delivery is recalculated after quantity changes and reloads so displayed
fees and totals use current prices and minimums. Empty-cart recent-order access
and existing shop delivery validation remain. Verified desktop/mobile, auto
pincode success/error recovery, quantity changes and final-item removal locally.

## Quantity contrast and preview checkout

The PHP stepper adapter now uses --on-brand for its buttons, matching the
reference orange stepper instead of painting orange symbols on orange. Both
server-rendered SVG controls and AJAX-created text controls were checked.
The guarded disposable Render initializer enables checkout_test_mode on startup,
including existing preview databases, with payments and messaging forced offline.
A labelled TEST / temporary manual payment permits review/test placement without
any provider charge. Production choices and live-payment requirements are unchanged.
Local Chromium verified adding, visible +/- before/after reload, delivery details,
review and final disposable test order creation.

Checkout no longer shows a delivery-area dropdown. The pincode resolves delivery
automatically; an area previously selected in the cart is retained only while
the checkout pincode matches that cart pincode. Editing the pincode drops that
old area selection. Ambiguous pincodes still require the cart's area choice;
checkout never guesses a charge or bypasses serviceability.

## Checkout validation matches the Python form flow

Review validation errors (HTTP 422) now re-render the checkout form with an
escaped alert rather than escaping to the plain application error page. Contact
and address inputs and payment choice retain submitted values. Mobile-number
format help explains the accepted ten-digit/country-code forms. Other HTTP
errors retain their existing handling. Chromium checked invalid phone and
unserviceable pincode, preserved fields, correction to review and final local
test placement. Phone validation itself remains enforced.
