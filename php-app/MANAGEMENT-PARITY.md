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
- 70 PHP behavioral checks and 546 PostgreSQL reference tests pass.

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
