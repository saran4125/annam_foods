"""Copy selected public Annam catalog fields and original assets into the preview."""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "wordpress" / "scripts"))
from fetch_annam import fetch, fetch_api, images  # noqa: E402

DEST = ROOT / "static" / "images" / "annam"
GROUPS = [
    ("breakfast", "Breakfast", "15th-monday-breakfast", 6),
    ("lunch", "Lunch", "02nd-saturday-lunch", 7),
    ("sweets", "Sweets", "sweets", 8),
    ("savouries", "Savouries", "pakshanams-1", 8),
    ("pantry", "Podis & pantry", "podi", 6),
    ("diwali", "Diwali 2026", "deepavli-2026-pakshanams", 6),
]
BRAND_ASSETS = {
    "logo": "https://cdn.commmerce.com/uploads/annams/settings/1703057700105716743216796390logo-1.png",
    "campaign": "https://cdn.commmerce.com/uploads/annams/media/2026/10/17913667748689Diwali-Banner.jpg",
    "campaign_mobile": "https://cdn.commmerce.com/uploads/annams/media/2026/10/17913667182193Diwali-Banner-Mobile.jpg",
}


def copy_asset(url):
    ext = Path(urlsplit(url).path).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ValueError("Unsupported source image")
    name = sha256(url.encode()).hexdigest()[:24] + ext
    destination = DEST / name
    existing = ROOT / "wordpress" / "data" / "assets" / name
    if not destination.exists():
        destination.write_bytes(existing.read_bytes() if existing.exists() else fetch(url, binary=True))
    return "/static/images/annam/" + name


def plain(value):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def read_group(group):
    key, label, category, limit = group
    listing = fetch_api("/products/productList/", {
        "page": 1, "limit": limit, "category": category, "sort": "featured", "filter": None,
    })
    return group, listing.get("products", [])[:limit]


def read_product(task):
    group, row = task
    info = fetch_api("/products/productDetails/", {"slug": row["slug"], "dummy": False}).get("productInfo", {})
    photos = images(info)
    if not photos:
        return None
    price = Decimal(str(info.get("sellingPrice", row.get("sellingPrice", "0"))).replace(",", ""))
    return {
        "id": row["slug"], "name": plain(info.get("name") or row["name"]),
        "price": str(price.quantize(Decimal("0.01"))), "category": group[0], "category_label": group[1],
        "description": plain(info.get("shortDescription")),
        "image": copy_asset(photos[0]), "source_image": photos[0],
        "source_url": "https://www.annamfood.in/products/" + row["slug"],
        "available": bool(info.get("available", True)),
    }


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(6) as pool:
        listings = list(pool.map(read_group, GROUPS))
    tasks = [(group, row) for group, rows in listings for row in rows]
    print(f"Reading {len(tasks)} original products", flush=True)
    with ThreadPoolExecutor(6) as pool:
        products = [product for product in pool.map(read_product, tasks) if product]
    brand = {key: copy_asset(url) for key, url in BRAND_ASSETS.items()}
    data = {
        "source": "https://www.annamfood.in/", "fetched_at": datetime.now(timezone.utc).isoformat(),
        "brand": brand,
        "categories": [{"id": key, "label": label} for key, label, _, _ in GROUPS],
        "products": products,
    }
    (ROOT / "static" / "annam-preview-catalog.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(products)} products and {len(list(DEST.iterdir()))} original assets", flush=True)


if __name__ == "__main__":
    main()
