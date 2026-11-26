# Python parity with the PHP rebuild — 26 November 2026

Ported the user-facing changes from PHP through `a16c1f3`, while retaining the
Django models, PostgreSQL tenant boundaries and existing payment integrations.
The PHP-specific Hostinger/SQLite and Render container setup are not applied to
the Python deployment, which continues to use its configured PostgreSQL service.

## Catalog and stock

- Four main library categories: Breakfast, Lunch, Dinner and Shop. Custom shelves
  remain available; existing categories, media, schedules and orders are kept.
- Meal membership can include all three meals without copying the product.
  Membership does not publish a menu. Dishes & products selects daily menus.
- Category counts have one item link; missing photos use a dish photo. Category
  deletion unfiles products and preserves stock/history. Default shelves remain.
- Pack-size and internal-note inputs are removed; their existing data is retained.
- Form switches are compact. Current pagination is highlighted with arrows.
- Snacks is no longer a meal time; shop delivery retains its own eligibility flag.
- Optional stock defaults off. Shop quantities are shared; meal quantities are
  separate for each meal/date. Set/add operations enforce revision checks.
- Website and staff orders reserve stock atomically, reject overselling, preserve
  retries, and release reservations once on cancellation. Zero is sold out.

## Checkout and documents

- Same signed guest browser can reuse its latest address for an exact pincode.
  A new pincode clears the old address and asks for a new one. No lookup by phone
  or pincode exposes another browser's address; the guest cookie lasts 30 days.
- Pincode changes clear area and estimates immediately. Multi-area pincodes need
  a selection. Coverage, charges and totals are independently rechecked on review
  and placement, including changes after the review page was opened.
- Shop category arrows and spacing match the rebuild. Existing Python cart,
  delivery/review/confirmation layouts and owned recent-order recovery are kept.
- Session-expired responses use the storefront layout and recovery actions.
- Issued COD invoices say Cash on delivery while remaining unsettled until cash
  is recorded. Collection no longer hides a saved address. Issued snapshots,
  amounts, numbering and settlement state are not rewritten for this display fix.
- Invoice browser PDF downloads use the receipt DOM and print CSS. This is an
  image-based PDF; browser Print / Save PDF retains selectable text. The native
  authenticated PDF remains the no-JavaScript/rendering-error fallback.
- Pending orders offer a clearly labelled order summary, not a tax invoice or
  proof of payment. An issued unpaid invoice can be downloaded without marking
  payment received. Browser/tenant ownership applies to every document route.

## Deployment

Apply additive migration `catalog.0007` before serving the updated Python app.
Existing build/start scripts run migrations. No stock or historical data import
from the temporary PHP preview is performed. HTML2PDF 0.14.0 is bundled locally
under its MIT license; no financial documents are sent to an external PDF service.

## Acceptance checks

683 PostgreSQL tests passed before release, including new stock, library,
address-isolation, pending-summary and COD snapshot tests. Both PHP database
suites pass 89 behavioral checks. Local browser acceptance covers desktop and
mobile library/checkout, actual COD invoices and receipt-layout PDF downloads,
repeat-order address restoration, fee changes, quantity entry and stock gates.
The health endpoint reports the public Render commit SHA when available so a
previous healthy deployment cannot be mistaken for the new one.

Production-style compressed manifest collection also passes. The PDF export
accepts hashed receipt stylesheets and loads the exact bundled library URL.
The bundle omits only its unavailable development source-map directive.
