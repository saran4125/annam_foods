# Annam Foods storefront improvements

## Status

The first local preview is complete. A second design refinement is in progress; its final visual and interaction checks are pending.

## Completed in the first preview

- Fixed UTF-8 rendering for punctuation and rupee prices.
- Added a local server that serves Home, Menu, Cart, About, Delivery and Refund URLs without the previous Menu 404.
- Replaced generated food photographs with original assets from Annam Foods.
- Imported 41 product records and 44 original assets, including the logo and Diwali banners.
- Preserved the orange-and-cream palette and Fraunces / Plus Jakarta Sans fonts.
- Added category filtering, dish search, price/name sorting and out-of-stock states.
- Added a browser-local cart with thumbnails, quantity controls, removal, persistence and exact integer-paise totals.
- Added responsive layouts, subtle entrance/hover/press motion and reduced-motion handling.
- Linked delivery and refund pages to the official Annam policies instead of inventing policy terms.

## Current refinement

- Reworking layout, typography and spacing for a more polished food storefront.
- Adding local product details, a quick cart panel and better catalog navigation.
- Improving mobile controls, safe-area spacing and keyboard interaction.
- Keeping existing routes, original product photographs and the established theme.

## Image and product sources

All displayed food images come from [Annam Foods](https://www.annamfood.in/) and its original CDN. No generated photographs are used. The rejected generated preview files were removed.

`static/annam-preview-catalog.json` records each product's original name, decimal price, availability, source product URL, original image URL and local image path. It is a snapshot, not a live stock feed. Daily meal dates and prices must be confirmed on the original site.

## Files

| File | Purpose |
| --- | --- |
| `storefront-preview.html` | Local preview shell and shared navigation |
| `static/preview.css` | Preview layout, visual styles and motion |
| `static/preview.js` | Preview navigation, catalog controls and cart |
| `static/annam-preview-catalog.json` | Original catalog snapshot and source attribution |
| `static/images/annam/` | Original Annam product and brand images |
| `scripts/preview_server.py` | Local HTTP server and working preview routes |
| `scripts/sync_preview_catalog.py` | Public catalog and original-image refresh |
| `docs/LOCAL_PREVIEW.md` | Run instructions and preview limitations |
| `docs/STOREFRONT_IMPROVEMENTS.md` | This work report |

## Run locally

From the repository root:

```powershell
python scripts/preview_server.py
```

Open [the local preview](http://127.0.0.1:8765/).

## Verification completed for the first preview

- HTTP 200 for every preview route and CSS, JavaScript and catalog files.
- Browser checks for Home, Menu, Cart, About, Delivery and Refund pages.
- Dish search, category filtering, price sorting and empty results.
- Cart add/increase/remove and persistence after refresh.
- Verified two ₹220 items produce a ₹440 subtotal.
- Verified out-of-stock products cannot be added.
- Desktop and 390px/320px viewport checks without horizontal overflow.
- No browser warnings/errors observed during the final checks.

## Limits

This is a standalone design preview, not the running Django ordering system. No customer authentication, delivery-zone validation, payment or order submission is connected. The preview cart does not transfer to Annam's website.

Mobile browser sizing has been tested, but real-phone touch, keyboard and safe-area behavior still needs hardware verification. Google Fonts requires internet access; local font fallbacks are provided.
