import hashlib
import json
from io import BytesIO

import pytest
from PIL import Image
from apps.catalog.models import MenuCategory, MenuItem
from apps.content.public_media import apply_originals, verified_assets
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


@pytest.fixture
def originals(settings, tmp_path):
    settings.BASE_DIR = tmp_path
    settings.MEDIA_ROOT = tmp_path / 'uploads'
    name = 'categories/' + 'a' * 32 + '.png'
    file = tmp_path / 'media' / name
    file.parent.mkdir(parents=True)
    buffer = BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
    file.write_bytes(buffer.getvalue())
    url = 'https://cdn.commmerce.com/diwali.png'
    asset = {'url': url, 'status': 'downloaded', 'path': name, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}
    deploy = tmp_path / 'deploy'
    deploy.mkdir()
    (deploy / 'annam_public_media.json').write_text(json.dumps({'assets': {'one': asset}}))
    matches = [{'url': url, 'kind': 'category', 'slug': 'diwali-2026'}, {'url': url, 'kind': 'product', 'source_id': 'diwali-sku'}]
    (deploy / 'annam_public_image_matches.json').write_text(json.dumps({'tenant': 'annam', 'matches': matches}))
    return name, file


@pytest.mark.django_db
def test_originals_fill_diwali_and_missing_product_images_only_for_annam(originals):
    name, _ = originals
    tenant = Tenant.objects.create(slug='annam', name='Annam')
    other = Tenant.objects.create(slug='other-originals', name='Other')
    with tenant_context(tenant):
        category = MenuCategory.objects.create(name='Diwali 2026', slug='diwali-2026')
        product = MenuItem.objects.create(name='Diwali sweet', retailer_id='diwali-sku', price='10')
    with tenant_context(other):
        foreign = MenuCategory.objects.create(name='Diwali', slug='diwali-2026')
    assert apply_originals(tenant)['updated'] == 2
    category.refresh_from_db(); product.refresh_from_db(); foreign.refresh_from_db()
    assert category.image.name == product.image.name == name
    assert foreign.image.name == ''
    assert product.price == 10
    assert apply_originals(tenant)['updated'] == 0


@pytest.mark.django_db
def test_existing_staff_upload_is_preserved_and_tampered_source_is_rejected(originals, settings):
    _, file = originals
    tenant = Tenant.objects.create(slug='annam', name='Annam')
    upload = settings.MEDIA_ROOT / 'categories/owner.png'
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b'owner original')
    with tenant_context(tenant):
        category = MenuCategory.objects.create(name='Diwali', slug='diwali-2026', image='categories/owner.png')
    assert apply_originals(tenant)['updated'] == 0
    category.refresh_from_db()
    assert category.image.name == 'categories/owner.png'
    file.write_bytes(b'tampered')
    assert verified_assets() == {}
