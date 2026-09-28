"""Attach a folder of photographs to menu items.

    ./manage.py import_menu_images --tenant example-kitchen --dir ~/Desktop/product-photos
    ./manage.py import_menu_images --tenant example-kitchen --dir ./photos --dry-run

Filenames are matched to dish names loosely -- case, spaces, hyphens,
underscores and bracketed quantities are all ignored -- so "Veg Meals" is
found by veg-meals.jpg, Veg_Meals.JPG or veg meals.png. Anything ambiguous or
unmatched is reported rather than guessed at, because silently attaching the
wrong photo to a dish is worse than attaching none.

Every kitchen needs this at onboarding, so it lives in the product rather than
in a one-off script.
"""
import re
import unicodedata
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import MenuItem
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}


def normalise(value: str) -> str:
    """Comparison key: lowercase letters and digits, everything else dropped."""
    value = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def keys_for(name: str) -> set[str]:
    """Every filename a person might reasonably use for this dish.

    "Idly (4)" is findable as idly-4.jpg (the count kept) or idly.jpg (the
    count dropped), because both are natural things to type.
    """
    return {normalise(name), normalise(re.sub(r"\(.*?\)", " ", name))}


class Command(BaseCommand):
    help = "Attach images from a folder to a tenant's menu items by filename."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="tenant slug")
        parser.add_argument("--dir", required=True, help="folder of images")
        parser.add_argument("--dry-run", action="store_true",
                            help="report what would happen, change nothing")
        parser.add_argument("--overwrite", action="store_true",
                            help="replace images on items that already have one")

    def handle(self, *args, **opts):
        try:
            tenant = Tenant.objects.get(slug=opts["tenant"])
        except Tenant.DoesNotExist:
            raise CommandError(f"No tenant with slug '{opts['tenant']}'.")

        folder = Path(opts["dir"]).expanduser()
        if not folder.is_dir():
            raise CommandError(f"{folder} is not a folder.")

        files = [p for p in sorted(folder.iterdir())
                 if p.is_file() and p.suffix.lower() in EXTENSIONS]
        if not files:
            raise CommandError(
                f"No images in {folder}. Looked for: {', '.join(sorted(EXTENSIONS))}"
            )

        attached, skipped, ambiguous, unmatched_items, unused = [], [], [], [], []

        with tenant_context(tenant):
            items = list(MenuItem.objects.all())

            # Resolve in both directions before writing anything. Two files
            # claiming one dish, or one file claiming two dishes, are both
            # reported rather than resolved by luck -- the wrong photograph on
            # a dish is worse than no photograph.
            claims: dict[int, list[Path]] = {item.pk: [] for item in items}
            for path in files:
                file_key = normalise(path.stem)
                matches = [i for i in items if file_key in keys_for(i.name)]
                if not matches:
                    unused.append(path.name)
                elif len(matches) > 1:
                    ambiguous.append(
                        (path.name, [f"matches {m.name}" for m in matches]))
                else:
                    claims[matches[0].pk].append(path)

            for item in items:
                candidates = claims[item.pk]
                if not candidates:
                    if not any(item.name in a[1][0] for a in ambiguous):
                        unmatched_items.append(item.name)
                    continue
                if len(candidates) > 1:
                    ambiguous.append((item.name, [c.name for c in candidates]))
                    continue
                if item.image and not opts["overwrite"]:
                    skipped.append(item.name)
                    continue

                source = candidates[0]
                if not opts["dry_run"]:
                    with source.open("rb") as fh:
                        item.image.save(source.name, File(fh), save=True)
                attached.append((item.name, source.name))

        w, s_, e = self.style.WARNING, self.style.SUCCESS, self.style.ERROR
        head = "Would attach" if opts["dry_run"] else "Attached"
        self.stdout.write(s_(f"{head} {len(attached)} image(s) to {tenant.name}"))
        for name, filename in attached:
            self.stdout.write(f"  {name}  ←  {filename}")

        if skipped:
            self.stdout.write(w(
                f"\nAlready had an image ({len(skipped)}) — pass --overwrite to replace:"))
            for name in skipped:
                self.stdout.write(f"  {name}")
        if ambiguous:
            self.stdout.write(e(f"\nAmbiguous, left alone ({len(ambiguous)}):"))
            for name, options in ambiguous:
                self.stdout.write(f"  {name}: {', '.join(options)}")
        if unmatched_items:
            self.stdout.write(w(f"\nNo photo found ({len(unmatched_items)}):"))
            for name in unmatched_items:
                self.stdout.write(f"  {name}")
        if unused:
            self.stdout.write(w(f"\nUnused files ({len(unused)}) — rename to match a dish:"))
            for filename in unused:
                self.stdout.write(f"  {filename}")

        if opts["dry_run"]:
            self.stdout.write(s_("\nDry run — nothing was changed."))
