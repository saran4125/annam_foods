# Annam public-source import · 28 September 2026

Source: `https://www.annamfood.in/` and its public catalog API over validated
HTTPS. The old live shop was read only.

| Reconciliation | Result |
|---|---:|
| Categories discovered | 34 |
| Unique products imported | 283 |
| Published products | 218 |
| Drafts requiring review | 65 |
| Downloaded source assets | 328 |
| Rerun | 283 unchanged, 0 duplicates, 0 owner conflicts |

Representative source-to-WooCommerce checks: Tirunelveli Halwa ₹220 with
250gm description and local product photo; Butter Murukku ₹140 with local
photo; Beetroot Vathal has a 200g WooCommerce option from the source option
data. The source's zero review counts and unsupported claims are not shown.

The public API returned no successful catalog data for
`daily-foods-1`, `kaju-sweets`, and `juices`. Those categories remain in the
report; the importer does not invent products or infer meal dates from their
names. The source campaigns and informational pages remain drafts pending
review. The Annam delivery window and zone tables are empty.

Validation: 36 PHP service and isolation checks; 35 HTTP checks covering
host rejection, separate storefront search and carts, server pricing,
checkout rejection, owner layout and product edits, and cross-store admin
access. Full machine-readable reports are regenerated locally under
`wordpress/reports/` and intentionally excluded from version control because
they can contain owner-edited content.
