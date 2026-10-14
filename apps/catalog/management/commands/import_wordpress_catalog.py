"""Import the local WordPress review catalog into Django as inactive drafts.

This command never fetches remote media. It only reads the catalog export and
its matching local asset map; use --apply to write rows and copy image files.
"""
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.html import strip_tags

from apps.catalog.models import MenuCategory, MenuItem
from apps.tenancy.context import all_tenants, tenant_context
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = "Preview or import the local WordPress catalog into a Django kitchen."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True)
        parser.add_argument(
            "--catalog", default=str(settings.BASE_DIR / "wordpress/data/catalog.json")
        )
        parser.add_argument(
            "--assets-dir", default=str(settings.BASE_DIR / "wordpress/data/assets")
        )
        parser.add_argument("--apply", action="store_true", help="Write draft catalog records.")
        parser.add_argument("--activate", action="store_true", help="Activate imported products after review.")

    def handle(self, *args, **options):
        path = Path(options["catalog"]).resolve()
        assets_dir = Path(options["assets_dir"]).resolve()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read catalog export: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("products"), list):
            raise CommandError("Catalog export must contain a products list.")

        with all_tenants():
            try:
                tenant = Tenant.objects.get(slug=options["tenant"])
            except Tenant.DoesNotExist as exc:
                raise CommandError(f"Unknown tenant: {options['tenant']}") from exc

        categories = data.get("categories", [])
        assets = data.get("assets", {})
        products = data["products"]
        seen = set()
        importable = []
        skipped = {"invalid_price": 0, "variants": 0, "missing_id": 0}
        for product in products:
            source_id = str(product.get("source_id") or "").strip()
            if not source_id:
                skipped["missing_id"] += 1
                continue
            if len(source_id) > 80:
                raise CommandError(f"source_id exceeds the 80-character retailer_id limit: {source_id[:80]}")
            if source_id in seen:
                raise CommandError(f"Duplicate source_id in export: {source_id}")
            seen.add(source_id)
            if product.get("variants") or product.get("variant_options"):
                skipped["variants"] += 1
                continue
            try:
                price = Decimal(str(product.get("price")))
                if not price.is_finite() or price <= 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError, TypeError):
                skipped["invalid_price"] += 1
                continue
            importable.append((product, source_id, price))

        if options["activate"] and not options["apply"]:
            raise CommandError("--activate requires --apply.")

        if not options["apply"]:
            self.stdout.write(
                f"Dry run for {tenant.slug}: {len(categories)} categories, "
                f"{len(importable)} products, {len(products) - len(importable)} skipped."
            )
            self.stdout.write("No database or media changes. Re-run with --apply to import drafts.")
            if any(skipped.values()):
                self.stdout.write("Skipped: " + ", ".join(f"{k}={v}" for k, v in skipped.items()))
            return

        category_names = {str(row.get("slug")): row.get("name", "") for row in categories}
        with transaction.atomic(), tenant_context(tenant):
            category_map = {}
            for sort, row in enumerate(categories):
                name = str(row.get("name", "")).strip()[:80]
                slug = str(row.get("slug", ""))
                if not name or not slug:
                    continue
                category, _ = MenuCategory.objects.get_or_create(
                    name=name, defaults={"sort": sort}
                )
                category_map[slug] = category

            created = updated = images = 0
            for product, source_id, price in importable:
                refs = product.get("categories") or []
                category = category_map.get(str(refs[0])) if refs else None
                fulfillment = "courier" if product.get("fulfilment") == "packaged_goods" else "scheduled"
                defaults = {
                    "name": str(product.get("name", "")).strip()[:120] or source_id,
                    "description": strip_tags(product.get("short_description") or "")[:4000],
                    "price": price,
                    "category": category,
                    "retailer_id": source_id[:80],
                    "fulfilment": fulfillment,
                    "active": bool(options["activate"]),
                    "tags": ["wordpress-import", "review-required"],
                }
                item, made = MenuItem.objects.get_or_create(
                    retailer_id=source_id[:80], defaults=defaults
                )
                if made:
                    created += 1
                else:
                    for field, value in defaults.items():
                        if field == "active" and not options["activate"]:
                            continue
                        setattr(item, field, value)
                    item.save()
                    updated += 1

                image_urls = product.get("images") or []
                filename = assets.get(image_urls[0]) if image_urls else None
                if filename and not item.image:
                    image_path = (assets_dir / filename).resolve()
                    if assets_dir not in image_path.parents or not image_path.is_file():
                        continue
                    safe_source_id = re.sub(r"[^A-Za-z0-9_-]", "_", source_id)[:80]
                    with image_path.open("rb") as image_file:
                        item.image.save(
                            f"wordpress-import/{safe_source_id}{image_path.suffix.lower()}",
                            File(image_file), save=True,
                        )
                    images += 1

        self.stdout.write(self.style.SUCCESS(
            f"Imported {created} products, updated {updated}, copied {images} images, "
            f"and created {len(category_map)} categories into {tenant.slug}."
        ))
        if any(skipped.values()):
            self.stdout.write("Skipped: " + ", ".join(f"{k}={v}" for k, v in skipped.items()))
        self.stdout.write("Imported products are drafts unless --activate was supplied.")
