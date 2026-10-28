# Annam ordering, delivery, courier collection and reporting

Implemented for the Django application from the owner's nine requirements and
confirmation that a combined order incurs **one delivery charge**. This supersedes
the earlier one-meal-only cart and flat statewide prepaid shop courier charge.

## Customer behavior

- Breakfast, Lunch and Snacks can be combined for the **same delivery date**.
  The same product selected in two food categories remains two distinct order
  lines with its own category and price snapshot.
- Dinner cannot be combined with any other category. The warning is exactly:
  “Dinner cannot be combined with other food categories. Please place a separate order for Dinner.”
- Local delivery requires an approved pincode and an area that serves **every**
  selected food category. Its fee is added once to the whole order, not once
  per category. Minimums apply to the combined items subtotal before delivery.
- The three restricted-coverage messages are the owner's exact Breakfast,
  Breakfast-and-Dinner, and Snacks-only messages. Unsupported selections cannot
  proceed to payment even when a request is submitted without browser controls.
- Pincode 600041 has Thiruvanmiyur ₹40 and Kottivakkam ₹60. Shared-pincode
  selections show the area and fee; both customer checkout and staff booking
  require the correct area. Existing other-area fees are not guessed or replaced.
- Further shared-pincode areas can be added under **Delivery areas**. The owner
  still needs to supply the names, fees and meal availability for the other
  approximately 3–4 shared pincodes; these values have not been invented.
- Scheduled Snacks use the Snacks meal tab. Packed shop goods use Snacks as
  their ordering/reporting group while retaining their catalog shelf category.

## Ordering windows

Under **Meal times**, each category now has:

1. **Orders open at** — local India time.
2. **Order days before** — 0 for the delivery date, 1 for the previous day.
3. **Orders close at** — local India time on the delivery date.

For Dinner open from today 10 AM until tomorrow 3 PM: set opening 10:00,
previous-day opening (1), and cutoff 15:00. Today/tomorrow menus continue to
use the saved daily menu resolver, holidays, stock and live price checks.
Every selected meal must still be within its own window at final submission.
Same-day opening must precede closing. No actual business cutoffs were guessed;
existing cutoffs remain until staff configure the approved timings.

## Outside-Chennai Snacks courier orders

An approved local pincode uses its area fee. Otherwise, outside-Chennai Indian
and international addresses use a deferred courier quote. An unapproved address
entered as Chennai must be corrected rather than silently given local delivery.
International courier addresses accept international-format phone numbers and
postal codes. Country/state/city are saved on the immutable order snapshot.

Before placing/paying for the food order, checkout displays the exact notice:

> Please note that courier charges are not included in the current order amount. The applicable courier charges will be confirmed after your order has been dispatched, and you will be required to pay the courier charges separately after dispatch.

No estimated flat courier charge is collected upfront. ₹0 on the stored food
order's delivery-fee field means **courier charge deferred**, not free delivery.
The UI, confirmation and food invoice explicitly explain the extra charge.

### Offline staff workflow

1. Receive the food payment and confirm it using the existing order screen.
2. Progress the order to **Out for delivery** after dispatch.
3. Enter the actual courier service, tracking number and courier amount in
   **Post-dispatch courier charge** on the order.
4. Communicate the held customer/team WhatsApp drafts manually.
5. After receiving the courier payment, confirm it separately with a reference.

The courier receivable has its own amount, dispatch and receipt timestamps and
reference. Saving it twice is idempotent. A confirmed charge cannot be casually
overwritten. It never modifies the original food payment, food total or bill.
A pending live online courier payment must be reconciled before recording a
manual courier payment, to prevent collecting the same charge twice.

### WhatsApp readiness — off by default

Disclosure, dispatch/amount and payment-received notices are persisted for both
the customer and the configured team phone, with deduplication keys. The team
phone defaults to the store's support number. While notifications are offline,
messages have **held** status and the sender does not deliver them. Their text
is available on the staff order page for manual communication.

After connecting and validating WhatsApp, configure the approved customer and
team templates under **Checkout settings**. Both templates use two body
parameters: order reference and notice text. This supports notices outside the
24-hour WhatsApp customer-service window. Automatic notifications require these
template names; old held drafts require an explicit, confirmed release action.
Template approval, correct provider credentials, n8n mapping and real delivery
still require external verification. Existing unrelated messaging is unchanged.

### Razorpay readiness — no live transaction performed

Food payments continue through the existing signed/verified payment flow with
the combined food amount and one local delivery fee. A deferred courier fee is
excluded from that payment.

A separately dispatched courier charge can use its own `CourierPayment` once
an enabled Razorpay connection exists and courier online payments are explicitly
enabled in Checkout settings. This switch defaults off. The guest's private order page exposes
that payment only when the charge is known and a connection is available. The
provider order amount is derived from the frozen courier charge, not a browser
value. Signatures, captured amount/currency/provider order, duplicate callbacks
and uncertain provider-order creation are checked. Test captures do not clear a
real courier receivable. Food and courier payment identities remain separate.

Real provider activation, international-payment eligibility, capture callbacks
and failure/reconciliation checks are launch work; mocked tests do not certify
those external services. Automatic courier refunds are not exposed in this UI;
any refund of that separate charge needs an explicit finance reconciliation.

## Reports and daily sales

**Order reports & sales** is available in the admin navigation and dashboard.

- Start/end **order-received** date/time, inclusive start and exclusive end.
- Optional delivery date, food category and product name/ID filters.
- Product quantity and item-value totals per food category (before order-level discounts), without adding
  delivery multiple times or confusing full-order value with product revenue.
- Downloadable CSV, with spreadsheet-formula escaping and explicit range metadata.
- Live access while ordering remains open. Refresh recomputes from the database.
- Today's order value, paid value of today's orders, awaiting-payment value
  and order count on the dashboard/report.
- Separate manual/online/courier receipt figures, verified online refunds and
  net receipts in expandable payment details. Receipt date and order date are
  different concepts and are labelled separately.
- Cancelled orders and Razorpay test orders excluded from sales. Detailed
  quantity reports may explicitly include cancelled orders.
- Old order snapshots are not rewritten. When old rows lack a food-category
  snapshot, reporting uses the stored order slot, or marks the row unclassified.
  Old rows without verified payment timestamps are not assigned guessed dates.

All reports remain tenant-scoped and require staff access. Reports are not cached.

## Deployment and verification

Run the standard deployment migration step; the release includes new fields
for meal opening windows, held notifications, a separate courier receivable,
verified payment timestamps and courier payment records. The area migration
applies the owner-approved 600041 split without rewriting issued order/bill data.
Future local seeds use the same split and include a Snacks slot.

The automated PostgreSQL suite and mocked provider tests cover combination
rules, exact warnings, shared-area selection, date/time boundaries, saved fees,
report quantities, tenant boundaries, notification deduplication and separate
courier verification. The Playwright review uses synthetic data only:

- [Browser checklist](examples/requirements-review/browser-checks.json)
- [Combined checkout](examples/requirements-review/combined-checkout.png)
- [Combined bill](examples/requirements-review/combined-bill.png)
- [Courier checkout](examples/requirements-review/courier-checkout.png)
- [Staff courier collection](examples/requirements-review/courier-staff.png)
- [Reports](examples/requirements-review/reports.png)

No live payment, refund or external WhatsApp message was executed during this work.
