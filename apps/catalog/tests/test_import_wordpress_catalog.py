import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from PIL import Image

from apps.catalog.models import MenuCategory, MenuItem
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


@pytest.fixture
def kitchen(db):
    return Tenant.objects.create(slug="catalog-import", name="Catalog Import")


def make_export(tmp_path, *, duplicate=False):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    Image.new("RGB", (8, 8), (20, 100, 120)).save(assets_dir / "dish.jpg")
    product_id = "SKU-1"
    products = [{
        "source_id": product_id, "name": "Festival Box", "price": "120.00",
        "description": "<p>Long description</p>", "short_description": "<p>Short</p>",
        "categories": ["sweets"], "fulfilment": "packaged_goods", "variants": [],
        "variant_options": [], "images": ["https://example.test/dish.jpg"],
    }]
    if duplicate:
        products.append(dict(products[0]))
    data = {
        "categories": [{"slug": "sweets", "name": "Sweets"}],
        "products": products,
        "assets": {"https://example.test/dish.jpg": "dish.jpg"},
    }
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(data))
    return catalog, assets_dir


@pytest.mark.django_db
def test_wordpress_catalog_import_defaults_to_a_dry_run(kitchen, tmp_path, capsys):
    catalog, assets = make_export(tmp_path)
    call_command("import_wordpress_catalog", tenant=kitchen.slug,
                 catalog=str(catalog), assets_dir=str(assets))
    assert "Dry run" in capsys.readouterr().out
    with tenant_context(kitchen):
        assert MenuItem.objects.count() == 0
        assert MenuCategory.objects.count() == 0


@pytest.mark.django_db
def test_wordpress_catalog_import_creates_inactive_items_and_copies_local_images(kitchen, tmp_path):
    catalog, assets = make_export(tmp_path)
    with override_settings(MEDIA_ROOT=tmp_path / "media"):
        call_command("import_wordpress_catalog", tenant=kitchen.slug,
                     catalog=str(catalog), assets_dir=str(assets), apply=True)
        with tenant_context(kitchen):
            item = MenuItem.objects.get(retailer_id="SKU-1")
            assert not item.active
            assert item.fulfilment == "courier"
            assert item.price == 120
            assert item.category.name == "Sweets"
            assert item.description == "Short"
            assert item.image
            assert item.image.storage.exists(item.image.name)
        call_command("import_wordpress_catalog", tenant=kitchen.slug,
                     catalog=str(catalog), assets_dir=str(assets), apply=True)
        with tenant_context(kitchen):
            assert MenuItem.objects.count() == 1


@pytest.mark.django_db
def test_wordpress_catalog_import_rejects_duplicate_source_ids(kitchen, tmp_path):
    catalog, assets = make_export(tmp_path, duplicate=True)
    with pytest.raises(CommandError, match="Duplicate source_id"):
        call_command("import_wordpress_catalog", tenant=kitchen.slug,
                     catalog=str(catalog), assets_dir=str(assets))
