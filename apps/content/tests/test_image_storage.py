from io import BytesIO, StringIO
from unittest.mock import patch

import pytest
from PIL import Image
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.content.local_images import local_image_url, localize_store_images
from apps.content.services import save_storefront_image, storefront_image_url
from apps.content.storage import BILL_LOGO, LEGACY_BILL_LOGO, editor_image_file, restore_bundled_media
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantDomain


def photo():
    output = BytesIO()
    Image.new('RGB', (8, 8), 'orange').save(output, format='PNG')
    return output.getvalue()


@pytest.fixture
def kitchen(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.SERVE_MEDIA = True
    tenant = Tenant.objects.create(slug='annam', name='Annam Foods')
    TenantDomain.objects.create(tenant=tenant, hostname='storage.localhost', is_primary=True)
    return tenant


def test_editor_images_are_files_and_draft_files_cannot_bypass_access_checks(kitchen, settings, client):
    image = save_storefront_image(kitchen, SimpleUploadedFile('photo.png', photo(), content_type='image/png'))
    relative = f'website/{kitchen.pk}/{image.pk}.png'
    assert (settings.MEDIA_ROOT / relative).read_bytes() == photo()
    url = storefront_image_url(kitchen, image)
    assert client.get(url, HTTP_HOST='storage.localhost').status_code == 404
    assert client.get('/media/' + relative, HTTP_HOST='storage.localhost').status_code == 404
    config = kitchen.config
    config.storefront_design = {'published': {'images': {'logo': url}}}
    config.save()
    response = client.get(url, HTTP_HOST='storage.localhost')
    assert response.status_code == 200
    assert b''.join(response.streaming_content) == photo()


def test_legacy_image_recovery_keeps_an_existing_media_replacement(kitchen, settings):
    image = save_storefront_image(kitchen, SimpleUploadedFile('photo.png', photo(), content_type='image/png'))
    path = settings.MEDIA_ROOT / f'website/{kitchen.pk}/{image.pk}.png'
    path.unlink()
    with editor_image_file(image) as file:
        assert file.read() == photo()
    path.write_bytes(b'existing replacement')
    with editor_image_file(image) as file:
        assert file.read() == b'existing replacement'


def test_bundled_logo_is_copied_into_media_without_overwriting_uploads(kitchen, settings):
    assert restore_bundled_media() >= 2
    logo = settings.MEDIA_ROOT / 'brand/annam-bill-logo.png'
    with Image.open(logo) as image:
        image.verify()
    logo.write_bytes(b'custom logo')
    assert restore_bundled_media() == 0
    assert logo.read_bytes() == b'custom logo'


def test_localizing_configuration_preserves_other_content_and_other_stores(kitchen):
    other = Tenant.objects.create(slug='other', name='Other')
    for tenant in (kitchen, other):
        config = tenant.config
        config.theme = {'billing_logo_url': LEGACY_BILL_LOGO, 'logo_url': '/media/custom.png', 'brand': '#123456'}
        config.home_sections = [{'kind': 'hero', 'title': 'Unchanged', 'link': 'https://www.annamfood.in/'}]
        config.save()
    call_command('materialize_media', tenant='annam', stdout=StringIO())
    kitchen.config.refresh_from_db()
    other.config.refresh_from_db()
    assert kitchen.config.theme == {'billing_logo_url': BILL_LOGO, 'logo_url': '/media/custom.png', 'brand': '#123456'}
    assert kitchen.config.home_sections[0]['link'] == 'https://www.annamfood.in/'
    assert other.config.theme['billing_logo_url'] == LEGACY_BILL_LOGO


def test_external_image_is_verified_and_stored_before_its_url_changes(kitchen, settings):
    config = kitchen.config
    source = 'https://cdn.commmerce.com/uploads/annams/photo.png'
    config.home_sections = [{'kind': 'spotlight', 'image': source, 'title': 'Keep this'}]
    config.save()
    with patch('apps.content.local_images.build_opener') as opener:
        opener.return_value.open.return_value = BytesIO(photo())
        assert localize_store_images(kitchen, download=True) == []
    config.refresh_from_db()
    url = config.home_sections[0]['image']
    assert url.startswith(f'/media/imported/{kitchen.pk}/')
    assert (settings.MEDIA_ROOT / url.removeprefix('/media/')).read_bytes() == photo()
    assert config.home_sections[0]['title'] == 'Keep this'
    with patch('apps.content.local_images.build_opener') as opener:
        assert localize_store_images(kitchen, download=True) == []
        opener.assert_not_called()


@pytest.mark.parametrize('url', ['https://127.0.0.1/secret', 'https://internal.example/a.png',
                               'http://cdn.commmerce.com/image.png',
                               'https://cdn.commmerce.com@localhost/photo.png'])
def test_unapproved_image_hosts_are_rejected_before_any_network_request(kitchen, url):
    with patch('apps.content.local_images.build_opener') as opener:
        with pytest.raises(ValueError):
            local_image_url(url, kitchen.pk, download=True)
        opener.assert_not_called()


def test_failed_download_keeps_the_original_image_reference(kitchen):
    config = kitchen.config
    source = 'https://cdn.commmerce.com/missing.png'
    config.home_sections = [{'image': source}]
    config.save()
    with patch('apps.content.local_images.build_opener') as opener:
        opener.return_value.open.return_value = BytesIO(b'not a photo')
        assert len(localize_store_images(kitchen, download=True)) == 1
    config.refresh_from_db()
    assert config.home_sections == [{'image': source}]
