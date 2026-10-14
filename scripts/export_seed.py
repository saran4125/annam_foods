"""Write deploy/annam_seed.json: the slice of wordpress/data/catalog.json that
scripts/seed_local.py needs (names, prices, shelves, photo addresses).

The full export is gitignored on purpose; this trimmed file has no photos in
it, only their public addresses, so the repository stays small.

    python scripts/export_seed.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = json.loads((ROOT / "wordpress" / "data" / "catalog.json").read_text(encoding="utf-8"))

categories = [
    {k: row.get(k) for k in ("source_id", "slug", "name", "parent_id", "image", "description")}
    for row in src["categories"]
]
products = []
for p in src["products"]:
    products.append({
        "source_id": p.get("source_id"),
        "name": p.get("name"),
        "short_description": p.get("short_description", ""),
        "description": p.get("description", ""),
        "price": p.get("price"),
        "variants": p.get("variants") or [],
        "variant_options": p.get("variant_options") or [],
        "categories": p.get("categories") or [],
        "images": (p.get("images") or [])[:1],
        "available": bool(p.get("available")),
        "fulfilment": p.get("fulfilment"),
    })

out = {
    "source": src.get("source"),
    "fetched_at": src.get("fetched_at"),
    "brand": {"logo": src["brand"]["logo"]},
    "categories": categories,
    "products": products,
    "assets": {},
}
dest = ROOT / "deploy" / "annam_seed.json"
dest.parent.mkdir(exist_ok=True)
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print(f"{dest.relative_to(ROOT)}: {dest.stat().st_size // 1024} KB, "
      f"{len(categories)} categories, {len(products)} products")
