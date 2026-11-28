# Sold-out meal visibility — 28 November 2026

Home meal previews and the customer menu now use published_menu: active dishes
selected for that date stay visible even when manually out of stock, optional
inventory reaches zero, or a legacy daily limit is exhausted. Each displays
Out of stock and has no Add/quantity/Choose ordering control. Date rows marked
unavailable and archived dishes stay hidden. Today/tomorrow use their own dated
inventory. Ordering services continue using the strict orderable resolver.

Validated with PostgreSQL regressions for today and tomorrow across manual,
quantity and legacy limits, hidden/removed rows and order rejection; Chromium
checks of both home pages/dated menus at desktop/mobile widths. PHP has matching
presentation and native SQLite/PostgreSQL checks. No inventory data is rewritten.
