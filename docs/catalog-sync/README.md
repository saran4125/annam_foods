# Reviewed Annam catalog sync — 30 October 2026

Implemented from the [owner-supplied task file](annam-sync-tasks.md).
The public source website could not be fetched in this execution environment
(the outbound proxy returned HTTP 403). This is a comparison to the uploaded
snapshot, **not a claim of a fresh live-site crawl**.

| Task | Result |
|---|---|
| 1 | All 29 listed in-stock products matched or created, prices updated, existing IDs/photos retained. Unknown photos use the existing storefront placeholder. Unknown pack sizes stay blank; internal review notes identify missing details. |
| 2 | Diwali 2026 contains 29 products in Combos, Sweets and Karams primary groups. Banner links to `/shop/diwali-2026/`; 5/7 November delivery dates remain visible. |
| 3 | Five confirmed price corrections applied. Mavadu Karam remains ₹280 pending pack-size confirmation before ₹450. |
| 4 | All 47 sold-out products exist and have stock disabled. They are hidden publicly and remain available for staff to switch on. |
| 5 | All 29 named existing products have stock disabled. Stock is a separate staff switch/filter; public shop, cart/order pricing, daily menus and staff billing respect it. |
| 6 | The 11 build-only products have internal review notes. They are preserved with their existing availability. |
| 7 | Approved subcategory families are linked; existing recorded source memberships assign parent-level products to the correct child. Featured products feed the existing home collection. Single primary categories are retained instead of duplicating products for Thokku cross-listing. |
| 8 | Explicit 31 October menus: 11 breakfast, 7 lunch and 7 dinner products, with date-specific prices. Existing staff-saved menus are preserved for review. Past-date menus are never written. No weekly schedule is inferred. |

## Deployment and repeatability

Migration `catalog.0006` adds stock, verified pack size, internal notes and a
per-store `CatalogSyncRun` audit record. The committed manifest is
[`deploy/annam_catalog_sync_20261030.json`](../../deploy/annam_catalog_sync_20261030.json).
The Render start script applies it once to an existing store before serving,
or after first provisioning. Later starts retain all staff changes. A changed
manifest requires a new reviewed version; an already-applied version cannot be
silently rewritten. Ambiguous shop matches stop and roll back the entire sync.

Run a database-only preview (no writes persist):

```bash
python manage.py sync_annam_catalog --tenant annam
```

Apply once and compare against the uploaded snapshot:

```bash
python manage.py sync_annam_catalog --tenant annam --apply
python manage.py audit_annam_catalog --tenant annam
```

The read-only audit exits with an error if required product stock, prices,
featured tags, the Diwali banner or the dated menus differ. Its output explicitly
states that external live verification has not been performed. A staff-saved
menu that differs from the file is reported for review rather than overwritten.
The sync audit records before/after catalog fields. No products, customers,
orders, payments, bills or historical price snapshots are deleted or repriced.
There are no Razorpay or WhatsApp provider calls in this process.

## Review evidence

On an isolated copy of the seed catalog the patch created 48 genuinely missing
products, reusing the other listed products instead of duplicating them. The
stored snapshot comparison has **zero differences**; the live production
result still depends on successful deployment and its own stored data.

- [Comparison and pending owner decisions](review/comparison.json)
- [Applied preview and before/after catalog values](review/applied-preview.json)
- [16 browser checks](review/browser-checks.json)
- [Diwali collection](review/diwali-collection.png)
- [Stock controls](review/stock-controls.png)
- [31 October lunch](review/october-31-lunch.png)
- [Mobile collection](review/diwali-mobile.png)

Validation: **626 PostgreSQL tests passed**, including dry-run rollback,
once-only application, ambiguous-match rollback, tenant isolation, past/staff menu
preservation, old-order snapshot preservation, direct stock bypass attempts and
stale-cart removal. Django checks, migration consistency and shell syntax pass.

Owner decisions still pending: Mavadu Karam pack size/price, the 11 build-only
products, Thokku cross-listing and the noted build-only daily dishes. Photos and
pack sizes flagged in the admin need verified source material. No invented
photos, weights or deletions were introduced.
