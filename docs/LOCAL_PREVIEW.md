# Annam storefront design preview

Run from the repository root:

```powershell
python scripts/preview_server.py
```

Open http://127.0.0.1:8765/ . Home, Menu, Cart, About, Delivery and Refund routes work directly and on refresh.

The preview preserves the orange/cream palette and Fraunces / Plus Jakarta Sans fonts. It uses 41 products and 44 original assets retrieved from Annam Foods, with source URLs and decimal prices in `static/annam-preview-catalog.json`. Photos are served locally; Google Fonts needs internet access and has local font fallbacks.

Features: category filtering, dish search, sorting, stock labels, a cart with thumbnails and exact integer-paise totals, browser persistence, responsive layouts, and motion that respects reduced-motion preferences. Meal dates and product stock are a catalog snapshot, not a live ordering feed.

This standalone preview does not run Django, authenticate customers, check delivery zones, or process orders/payments. Its cart cannot transfer to the original website. Information pages link to Annam's current official policies.

Refresh selected products from Annam's public catalog using:

```powershell
python scripts/sync_preview_catalog.py
```

The sync script verifies HTTPS and copies original product images. It makes only public category/product read requests. Generated food images are not used.

## Running the real Django storefront locally (no Docker or Postgres)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```

Open http://annam.localhost:8000/ (`*.localhost` resolves to your own PC).
This uses `config/settings/local.py` (SQLite, tasks run inline) and
`scripts/seed_local.py`, which loads Annam's full public catalog from
`wordpress/data/catalog.json` (141 shop products, 22 daily meals, 34 shelves,
local photos) plus Annam's real contact details, FSSAI number and Diwali banner.
Re-run the seed script any time to reset the demo kitchen.
Local-only: tests and production stay on PostgreSQL.

Demo values the owner must replace: meal cutoffs and delivery windows,
Chennai delivery zones and fees, and the shipping/refund/privacy page text.

Pages: `/` home, `/menu/` daily meals by slot, `/shop/` and `/shop/<shelf>/`
courier goods with search and sort, `/item/<id>/` product page, `/cart/`.

UI lives in `templates/`, `static/css/storefront.css` and `static/js/storefront.js`.

## Owner admin (`/manage/`)

http://annam.localhost:8000/manage/ — the kitchen owner's backend. The local
demo login is defined at the top of `scripts/seed_local.py` (`OWNER_USERNAME`
/ `OWNER_PASSWORD`); never reuse it anywhere real.

Dashboard, orders (with status changes), dishes & products (add, rename,
reprice, photo upload, daily-menu days, featured, on/off), categories, meal
times, offer banners, pages, delivery areas, and store settings (name, logo,
brand colour, announcements, home hero text, website ordering / shop on-off).
Access requires a TenantUser membership for this kitchen (or a superuser).
