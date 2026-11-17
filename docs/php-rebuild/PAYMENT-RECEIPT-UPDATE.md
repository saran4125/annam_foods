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
