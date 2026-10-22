# Bill layout concepts — choose one before implementation

These are design proposals, not the current invoice template. All three use the
same illustrative order: Idly (4) × 2 = ₹220, Ghee Pongal = ₹110, delivery = ₹30;
total ₹360. Zero GST is used only for this unregistered-business example. Actual
GST document titles, seller/buyer fields and tax breakdown must follow the saved
billing profile when implementing the selected layout.

- **Option 1 — Branded modern:** warm Annam colours, strong header, separated
  customer/delivery panel and clear totals. Recommended for customer-facing bills.
- **Option 2 — Formal invoice:** restrained print-friendly structure, detailed
  item/SAC table, buyer/shipping columns and tax summary.
- **Option 3 — Compact receipt:** one-column hierarchy, prominent paid amount,
  simple item details and a narrow reading area for easy sharing.

Open `comparison.png` for all three together, or `option-1.png`, `option-2.png`
and `option-3.png` at full size. Matching one-page A4 PDFs and self-contained HTML
files are included. `index.html` presents the concepts together in a browser.

All customer, licence, payment and item-description details are illustrative.
No order, payment, invoice sequence or production template was changed.
