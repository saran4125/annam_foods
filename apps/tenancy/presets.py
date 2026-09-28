"""Validated, idempotent site defaults loaded only when a kitchen is created."""
from pathlib import Path
import yaml
from django.conf import settings

from .features import validate_features

PRESET_DIR = settings.BASE_DIR / "presets"


def preset_names():
    return sorted(path.stem for path in PRESET_DIR.glob("*.yaml"))


def load_preset(name: str) -> dict:
    if name not in preset_names():
        raise ValueError(f"Unknown preset: {name}")
    data = yaml.safe_load((PRESET_DIR / f"{name}.yaml").read_text())
    if not isinstance(data, dict):
        raise ValueError("A preset must be a mapping.")
    if data.get("name") != name:
        raise ValueError("Preset name differs from its filename.")
    validate_features(data.get("features", {}))
    for slot in data.get("slots", []):
        if set(slot) - {"key", "label", "order_cutoff", "delivery_from", "delivery_to", "sort"}:
            raise ValueError("Unknown slot field in preset.")
        if not all(slot.get(k) for k in ("key", "label", "order_cutoff")):
            raise ValueError("Every slot needs a key, label and cutoff.")
    for page in data.get("pages", []):
        if not all(page.get(k) for k in ("slug", "title")):
            raise ValueError("Every sample page needs a slug and title.")
    return data


def apply_preset(tenant, name: str) -> None:
    from apps.catalog.models import Slot
    from apps.content.models import Page
    from .context import tenant_context

    data = load_preset(name)
    with tenant_context(tenant):
        config = tenant.config
        config.preset_name = name
        config.preset_data = {
            "copy": data.get("copy", {}), "template_pack": data.get("template_pack", []),
        }
        config.theme = data.get("theme", {})
        config.features = validate_features(data.get("features", {}))
        config.menu_mode = data.get("menu_mode", "daily")
        config.save()
        for row in data.get("slots", []):
            Slot.objects.get_or_create(key=row["key"], defaults=row)
        for row in data.get("pages", []):
            Page.objects.get_or_create(slug=row["slug"], defaults={
                "title": row["title"], "body_md": row.get("body_md", ""),
                "published": False,
            })
