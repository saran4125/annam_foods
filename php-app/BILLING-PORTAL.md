# Billing portal parity and later collection

PHP now has a dedicated `/billing/` workspace using the Python billing stylesheet,
sidebar structure and searchable meal-aware item picker. Existing PHP staff
accounts work at `/billing/login/`; the general management panel stays separate.

| Python workflow | PHP route / behavior |
| --- | --- |
| Billing overview and source counts | `/billing/` |
| Manual / website / WhatsApp orders | `/billing/manual/`, `/billing/web/`, `/billing/whatsapp/` |
| Search, paid/unpaid filters, pagination | Source lists, 25 orders per page, scoped snapshot-name lookup |
| New booking and meal picker | `/billing/new/`, multiple item rows, quantities, live server prices |
| Staff-only saved customer lookup | `/billing/customer-lookup/` |
| Shared seller/tax/numbering settings | `/billing/settings/`, existing financial snapshots unchanged |
| Order detail and payment controls | `/billing/orders/<id>/` |
| Payment not received / collect on delivery | Existing COD unpaid state; no invoice allocation |
| Delivered while payment outstanding | Remains unpaid; delivery never confirms receipt |
| Confirm actual collection | Full-receipt confirmation required; one immutable invoice |
| View/print and download | `/billing/bills/<id>/` and `download/` |
| Online verification and test protection | Reuses payment provider guards; no manual online settlement or test invoice |
| Authorization | Existing staff session, scoped tenant SQL, POST CSRF; owner-only financial settings |

Browser checks cover desktop and mobile routes, booking, picker meal selection,
collection deferral, delivery status changes, later confirmation, invoice/PDF,
search filters, unknown-order denial and CSRF. Behavioral tests cover idempotency,
prices, unpaid invoice rejection and prevention of paid-to-unpaid reversal.
Python has the same new collection option and separate payment/fulfilment states.

These checks do not certify real Razorpay credentials, charges or refund
acceptance. The shared invoice print layout is retained. Install the full private
code and public assets from the update ZIP together; preserve `.env`, database,
installation state, accounts, orders and uploaded media. No production rows were
changed for this update.

Website billing clarification: orders arranged for manual payment also show the
Payment not received / collect on delivery action. This does not enable COD for
normal online checkout or convert Razorpay orders to manual payments. Online
orders show a read-only unpaid status and stay provider-verified. Paid, refunded,
cancelled and invoiced records retain their existing protections.

### Bills before collection
Staff can explicitly choose **Issue bill — payment not received** for an active
manual-payment or cash-on-delivery order. The bill and PDF show UNPAID and the
amount due. Issuance and delivery do not mark payment received. Confirm actual
collection later on the billing order; the existing bill number and frozen
financial snapshots are reused. Online/provider and simulated payments cannot
use this action. Automatic issuance continues to require verified payment.
