"""Fill a local SQLite database with Annam Foods so the storefront has real
content to show. Safe to re-run; it rebuilds the demo kitchen each time.

    python scripts/seed_local.py

Data: deploy/annam_seed.json (committed, no photos) when present, otherwise the
full export in wordpress/data/catalog.json. Photos come from
wordpress/data/assets when they exist locally; with SEED_DOWNLOAD_ASSETS=1 any
missing photo is downloaded once from Annam's public image address.

Environment (all optional locally, used by the Render deploy):
  DJANGO_SETTINGS_MODULE   defaults to config.settings.local
  SEED_DOMAIN              hostname of the storefront (default annam.localhost)
  SEED_OWNER_USERNAME      owner login (default annam-owner)
  SEED_OWNER_PASSWORD      REQUIRED outside config.settings.local
  SEED_ONLY_IF_EMPTY=1     do nothing when the kitchen already exists, so a
                           redeploy never wipes the owner's edits

Demo-only values, to be replaced by the owner: meal slot cutoffs and delivery
windows, delivery zones and fees, and the policy page text.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from datetime import time
from decimal import Decimal, InvalidOperation
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402

from django.utils.html import strip_tags  # noqa: E402

from apps.catalog.models import (  # noqa: E402
    MenuCategory, MenuItem, MenuSchedule, ScheduleMode, Slot,
)
from apps.content.models import Banner, Page  # noqa: E402
from apps.delivery.models import DeliveryZone  # noqa: E402
from apps.tenancy.context import all_tenants, tenant_context  # noqa: E402
from apps.tenancy.models import (  # noqa: E402
    BillingProfile, Tenant, TenantConfig, TenantDomain, TenantStatus, TenantUser, TenantUserRole,
)
from django.contrib.auth import get_user_model  # noqa: E402

_SEED_FILE = ROOT / "deploy" / "annam_seed.json"
_FULL_EXPORT = ROOT / "wordpress" / "data" / "catalog.json"
EXPORT = json.loads((_FULL_EXPORT if _FULL_EXPORT.exists() else _SEED_FILE).read_text(encoding="utf-8"))
ASSETS = ROOT / "wordpress" / "data" / "assets"
ASSET_MAP = EXPORT["assets"]
MEDIA = Path(settings.MEDIA_ROOT)
DOWNLOAD = os.environ.get("SEED_DOWNLOAD_ASSETS") == "1"
DOMAIN = os.environ.get("SEED_DOMAIN", "annam.localhost").strip().lower()

# Local-only demo login for the owner backend at /manage/. Never reuse these
# anywhere real; production owners are created with provision_tenant.
OWNER_USERNAME = os.environ.get("SEED_OWNER_USERNAME", "annam-owner")
OWNER_PASSWORD = os.environ.get("SEED_OWNER_PASSWORD") or (
    "annam-local-demo-2026" if os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings.local" else ""
)
if not OWNER_PASSWORD:
    sys.exit("SEED_OWNER_PASSWORD is required outside config.settings.local.")

# Meal categories in the export are dated ("29th Tuesday Lunch"); the slot
# is in the name. Demo cutoffs: the owner sets the real ones.
SLOTS = [
    ("breakfast", "Breakfast", time(6, 30), time(7, 30), time(9, 30)),
    ("lunch", "Lunch", time(10, 30), time(12, 30), time(14, 0)),
    ("dinner", "Dinner", time(18, 0), time(19, 30), time(21, 0)),
]
FEATURED_SHELF = "always-loved-by-everyone-this-products"
HIDDEN_SHELVES = {FEATURED_SHELF, "daily-foods-1"}  # a tag and a meal umbrella, not shop shelves
# Shop shelf order: what customers come for first.
SHELF_ORDER = ["podi", "pakshanams-1", "sweets", "pickles", "health-products", "laddus-1", "thokku",
               "vathal-vadagams", "rice-mix-paste", "ready-to-cook", "rasam-paste", "appalams", "diary"]
ZONES = [  # demo fees around Triplicane
    ("600005", "Triplicane", "30", "200"), ("600004", "Mylapore", "40", "250"),
    ("600014", "Royapettah", "40", "250"), ("600017", "T. Nagar", "60", "300"),
    ("600028", "R.A. Puram", "60", "300"), ("600020", "Adyar", "70", "350"),
]


def asset_for(url):
    if not url or "/placeholders/" in url:  # the old site's generic "no image" art
        return None
    name = ASSET_MAP.get(url)
    path = ASSETS / name if name else None
    if path and path.is_file():
        return path
    if not DOWNLOAD:
        return None
    ext = Path(url.split("?")[0]).suffix.lower() or ".jpg"
    path = ASSETS / (hashlib.sha256(url.encode()).hexdigest()[:24] + ext)
    if not path.is_file():
        try:
            ASSETS.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "SeerKitchen-seed/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:  # https only: Annam's public CDN
                path.write_bytes(resp.read())
        except Exception as exc:  # a missing photo must not stop the kitchen from seeding
            print(f"  photo skipped ({exc.__class__.__name__}): {url[-60:]}")
            return None
    return path


def prefetch_assets():
    """Download every photo up front, eight at a time, so the seed itself never
    waits on the network one image at a time."""
    if not DOWNLOAD:
        return
    from concurrent.futures import ThreadPoolExecutor

    urls = {EXPORT["brand"]["logo"]}
    urls |= {c.get("image") for c in EXPORT["categories"]}
    urls |= {u for p in EXPORT["products"] for u in (p.get("images") or [])[:1]}
    urls |= {"https://cdn.commmerce.com/uploads/annams/media/2026/10/17913667748689Diwali-Banner.jpg"}
    urls = [u for u in urls if u]
    print(f"Downloading up to {len(urls)} photos...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(asset_for, urls))


def copy_media(src: Path, folder: str) -> str:
    rel = f"{folder}/{src.name}"
    dest = MEDIA / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(src, dest)
    return rel


def clean_text(raw: str, limit=600) -> str:
    # Tags become spaces first: "<b>500gm</b><div>Kambu" must not read "500gmKambu".
    text = strip_tags(re.sub(r"<[^>]+>", " ", unescape(raw or ""))).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def clean_name(raw: str) -> str:
    """Source names carry date prefixes, internal codes and typos."""
    name = re.sub(r"\s+", " ", raw).strip()
    name = re.sub(r"^\d{1,2}(st|nd|rd|th|tth)\s+", "", name, flags=re.I)
    name = re.sub(r"^(Bf|Dr)\s*-?\s+", "", name)              # breakfast / dinner codes
    name = re.sub(r"^Sing(le|el) Pack\s*-\s*", "", name)      # "Single Pack - Tomato Rasam"
    name = re.sub(r"\s*-\s*", " - ", name)
    for bad, good in [("Spl ", "Special "), ("Mixutre", "Mixture"), ("Pakshanms", "Pakshanams"),
                      ("Vegitable", "Vegetable"), ("Leavs", "Leaves"), ("Pck", "Pack"),
                      ("Chapapthi", "Chapathi"), ("Hawa", "Halwa"), ("Vadai - 1", "Vadai (1)"),
                      ("Diary", "Dairy")]:
        name = name.replace(bad, good)
    if name in ("With Rice", "Without Rice"):
        name = f"Full meals {name.lower()}"
    return name[:120]


def slot_for(category_name: str) -> str:
    lowered = category_name.lower()
    for key in ("breakfast", "dinner", "lunch"):
        if key in lowered:
            return key
    return "lunch"


# -- tenant -------------------------------------------------------------------

with all_tenants():
    if os.environ.get("SEED_ONLY_IF_EMPTY") == "1" and Tenant.objects.filter(slug="annam").exists():
        print("Annam already exists; leaving it untouched.")
        sys.exit(0)
    prefetch_assets()
    for old in Tenant.objects.filter(slug="annam"):
        with tenant_context(old):  # PROTECTed FKs: dishes go before their shelves
            MenuItem.objects.all().delete()
            MenuCategory.objects.all().delete()
        old.delete()
    tenant = Tenant.objects.create(
        slug="annam", name="Annam Foods", primary_domain=DOMAIN,
        status=TenantStatus.ACTIVE,
    )
    TenantDomain.objects.create(tenant=tenant, hostname=DOMAIN, is_primary=True)

logo = asset_for(EXPORT["brand"]["logo"])
TenantConfig.objects.filter(tenant=tenant).update(
    brand_name="Annam Foods",
    tagline="Home-made Brahmin meals, podis, sweets and pickles from Triplicane, Chennai",
    support_phone="+91 95510 79550",
    theme={
        "brand": "#FF8507",
        "brand_dark": "#1C1C1C",
        "logo_url": "/media/" + copy_media(logo, "brand") if logo else "",
        "contact_email": "annamsfoods@gmail.com",
        "announcements": [
            "Chennai’s home-made Brahmin food store",
            "Daily breakfast, lunch & dinner — order before the cutoff",
            "Podis, pakshanams & sweets shipped fresh",
            "Bookings & doubts: WhatsApp 95510 79550",
        ],
    },
    features={"website_ordering": True, "snacks_courier": True},
)
BillingProfile.objects.update_or_create(
    tenant=tenant,
    defaults={"legal_name": "Annam Foods", "address": "Triplicane, Chennai 600005",
              "state": "Tamil Nadu", "state_code": "33", "fssai_no": "22424533000560"},
)

with tenant_context(tenant):
    # -- shelves ----------------------------------------------------------
    by_source, by_slug = {}, {}
    for sort, row in enumerate(EXPORT["categories"]):
        slug = row["slug"]
        image = asset_for(row.get("image"))
        category = MenuCategory.objects.create(
            name=clean_name(row["name"])[:80], slug=slug,
            sort=SHELF_ORDER.index(slug) if slug in SHELF_ORDER else 50 + sort,
            description=clean_text(row.get("description", ""), 300),
            image=copy_media(image, "categories") if image else "",
            active=slug not in HIDDEN_SHELVES,
        )
        by_source[str(row["source_id"])] = category
        by_slug[slug] = category
    for row in EXPORT["categories"]:
        parent = by_source.get(str(row.get("parent_id")))
        if parent and parent.slug not in HIDDEN_SHELVES:
            child = by_slug[row["slug"]]
            child.parent = parent
            child.save(update_fields=["parent"])

    slots = {}
    for sort, (key, label, cutoff, d_from, d_to) in enumerate(SLOTS, 1):
        slots[key] = Slot.objects.create(key=key, label=label, order_cutoff=cutoff,
                                         delivery_from=d_from, delivery_to=d_to, sort=sort)

    # -- products ---------------------------------------------------------
    shop = meals = 0
    health_mix = None
    for sort, p in enumerate(EXPORT["products"]):
        try:
            price = Decimal(str(p.get("price")))
        except (InvalidOperation, TypeError):
            continue
        if price <= 0 or p.get("variants"):
            continue
        refs = [r for r in p.get("categories") or [] if r in by_slug]
        shelves = [by_slug[r] for r in refs if r not in HIDDEN_SHELVES]
        # Most specific shelf wins: Murukku over Pakshanams.
        shelf = next((c for c in shelves if c.parent_id), shelves[0] if shelves else None)
        image = asset_for((p.get("images") or [None])[0])
        courier = p.get("fulfilment") == "packaged_goods"
        item = MenuItem.objects.create(
            name=clean_name(p["name"]),
            description=clean_text(p.get("short_description") or p.get("description")),
            price=price, category=shelf, sort=sort, is_veg=True,
            retailer_id=str(p["source_id"])[:80],
            fulfilment="courier" if courier else "scheduled",
            active=bool(p.get("available")),
            image=copy_media(image, "menu") if image else "",
            tags=["featured"] if FEATURED_SHELF in refs else [],
        )
        if courier:
            shop += int(item.active)
            if item.retailer_id == "HM2":
                health_mix = item
        elif item.active:
            slot = slots[slot_for(shelf.name if shelf else p["name"])]
            for weekday in range(7):
                MenuSchedule.objects.create(item=item, slot=slot, mode=ScheduleMode.WEEKDAY, weekday=weekday)
            meals += 1

    # Shelves without their own photo borrow their first product's.
    for category in MenuCategory.objects.filter(image=""):
        first = MenuItem.objects.filter(category=category).exclude(image="").first()
        if first:
            category.image = first.image.name
            category.save(update_fields=["image"])

    # -- campaigns, pages, zones -----------------------------------------
    diwali = asset_for("https://cdn.commmerce.com/uploads/annams/media/2026/10/17913667748689Diwali-Banner.jpg") \
        or (ROOT / "static" / "images" / "annam" / "9426c21fe7638efaed84f274.jpg")
    if diwali.is_file():  # no banner at all is better than a broken one
        Banner.objects.create(title="Diwali 2026 sweets & pakshanams",
                              subtitle="Mega Combo, Karam Combo, Sweets Combo and assorted sweets — "
                                       "delivered on 5th & 7th November. Book early.",
                              image=copy_media(diwali, "banners"),
                              link="/shop/deepavli-2026-pakshanams/" if "deepavli-2026-pakshanams" in by_slug else "/shop/",
                              sort=0)

    health_art = asset_for("https://cdn.commmerce.com/uploads/annams/wbImages/17280598825665Health-Mix.jpg")
    if health_mix:
        TenantConfig.objects.filter(tenant=tenant).update(home_sections=[{
            "kind": "hero",
            "kicker": "Home-made Brahmin kitchen · Triplicane, Chennai",
            "title": "Home food, cooked fresh for your table every day.",
            "body": "Idly, pongal and full meals cooked to your slot — plus podis, pakshanams, sweets and "
                    "pickles made in small batches and shipped fresh across Chennai.",
        }, {
            "kind": "spotlight",
            "kicker": "Annam’s Health Mix",
            "title": "Seventeen grains, one warm cup.",
            "body": "Our special health mix is stone-ground from millets, heritage rice, pulses and nuts — "
                    "a nourishing kanji for the whole family.",
            # The 17 ingredients listed on annamfood.in (Tamil originals, in English)
            "points": ["Kambu", "Ragi", "Thinai", "Varagu", "Samai", "Kuthiraivali",
                       "Boiled rice", "Samba wheat", "Karuppu kavuni rice", "Mappillai samba rice",
                       "White jowar", "Hand-pounded rice", "Almonds", "Roasted gram", "Sago",
                       "Walnuts", "Green gram"],
            "badge": f"₹{health_mix.price:.0f} · 500 g",
            # The product photo, not the campaign art: that artwork prints an old price (Rs.350).
            "image": health_mix.image.url if health_mix.image else (
                "/media/" + copy_media(health_art, "campaigns") if health_art else ""),
            "link": f"/item/{health_mix.pk}/",
            "cta": "Order Health Mix",
        }])

    for slug, title, body in [
        ("about", "About us",
         "Annam Foods is a home-style Brahmin kitchen in **Triplicane, Chennai**.\n\n"
         "Every day we cook breakfast, lunch and dinner to order, the way it is made at home. "
         "Alongside the daily menu we prepare podis, pakshanams, sweets, pickles, vathals and health "
         "mixes in small batches, packed fresh and shipped to your door.\n\n"
         "For bookings and questions, message us on WhatsApp **95510 79550** or write to annamsfoods@gmail.com."),
        ("shipping-policy", "Shipping policy", "Shipping terms will appear here once confirmed by Annam."),
        ("refund-policy", "Refund policy", "Our refund policy will appear here once confirmed by Annam."),
        ("privacy-policy", "Privacy policy", "Our privacy policy will appear here once confirmed by Annam."),
    ]:
        Page.objects.create(slug=slug, title=title, body_md=body, published=True,
                            show_in_nav=(slug == "about"))

    for pincode, area, fee, minimum in ZONES:
        DeliveryZone.objects.create(pincode=pincode, area_name=area,
                                    delivery_fee=Decimal(fee), min_order=Decimal(minimum))

owner, _ = get_user_model().objects.get_or_create(username=OWNER_USERNAME)
owner.set_password(OWNER_PASSWORD)
owner.save()
TenantUser.all_tenants.create(tenant=tenant, user=owner, role=TenantUserRole.OWNER)

print(f"Seeded Annam Foods: {shop} shop products, {meals} daily meals, {len(by_slug)} categories")
print(f"Owner backend: https://{DOMAIN}/manage/ (username {OWNER_USERNAME})" if DOMAIN != "annam.localhost"
      else "Owner backend: http://annam.localhost:8000/manage/ (demo login: see OWNER_USERNAME in this script)")
