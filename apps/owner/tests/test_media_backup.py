import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth import get_user_model

from apps.catalog.models import MenuCategory, MenuItem
from apps.content.backups import build_media_backup
from apps.content.models import Banner, StorefrontImage
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantDomain, TenantUser

HOST = 'backup.localhost'


@pytest.fixture
def store(db, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    tenant = Tenant.objects.create(slug='annam', name='Annam Foods')
    TenantDomain.objects.create(tenant=tenant, hostname=HOST, is_primary=True)
    user = get_user_model().objects.create_user('backup-owner')
    with tenant_context(tenant):
        TenantUser.objects.create(user=user, role='owner')
    return tenant, user


def read_zip(response):
    data = b''.join(response.streaming_content)
    response.close()
    return ZipFile(BytesIO(data))


def test_owner_download_contains_only_store_images_and_reports_missing_files(store, client, settings):
    tenant, user = store
    for name in ('menu/dish.png', 'categories/shelf.png', 'banners/offer.png', 'brand/logo.png',
                 'menu/unreferenced.png', 'menu/rival.png', 'private-bill.pdf', '.env'):
        path = settings.MEDIA_ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    with tenant_context(tenant):
        MenuItem.objects.create(name='Dish', price=100, image='menu/dish.png')
        MenuItem.objects.create(name='Unavailable photo', price=100, image='menu/lost.png')
        MenuCategory.objects.create(name='Shelf', image='categories/shelf.png')
        Banner.objects.create(title='Offer', image='banners/offer.png')
    other = Tenant.objects.create(slug='rival', name='Rival')
    with tenant_context(other):
        MenuItem.objects.create(name='Other dish', price=100, image='menu/rival.png')
    config = tenant.config
    config.theme = {'logo_url': '/media/brand/logo.png', 'billing_logo_url': '/static/branding/annam-bill-logo.png'}
    config.home_sections = [{'image': 'https://example.test/image.png?private-token=do-not-export'}]
    config.save()
    client.force_login(user)
    response = client.post('/manage/settings/media-backup/', HTTP_HOST=HOST)
    assert response.status_code == 200
    assert 'no-store' in response['Cache-Control']
    assert response['Content-Type'] == 'application/zip'
    assert response['X-Backup-Missing-Count'] == '1'
    with read_zip(response) as archive:
        names = set(archive.namelist())
        assert names == {'media/menu/dish.png', 'media/categories/shelf.png', 'media/banners/offer.png',
                         'media/brand/logo.png', 'media/brand/annam-bill-logo.png', 'README.txt', 'backup-report.json'}
        assert archive.read('media/menu/dish.png') == b'menu/dish.png'
        report = json.loads(archive.read('backup-report.json'))
        assert report['image_count'] == 5
        assert report['missing_files'] == [{'path': 'menu/lost.png', 'reason': 'File missing or unreadable'}]
        assert report['external_images_not_included'] == ['https://example.test/image.png']


def test_export_includes_legacy_draft_photos_without_mutating_the_database(store):
    tenant, _ = store
    with tenant_context(tenant):
        image = StorefrontImage.objects.create(name='draft.png', data=b'draft image', content_type='image/png',
                                               width=1, height=1)
    archive_file, _ = build_media_backup(tenant)
    with archive_file, ZipFile(archive_file) as archive:
        assert archive.read(f'media/website/{tenant.pk}/{image.pk}.png') == b'draft image'
    image.refresh_from_db()
    assert bytes(image.data) == b'draft image'
    assert tenant.config.storefront_design == {}


@pytest.mark.parametrize('role', ['staff', 'manager', None])
def test_nonowners_cannot_export_or_see_the_download_button(store, client, role):
    tenant, _ = store
    user = get_user_model().objects.create_user('nonowner')
    if role:
        with tenant_context(tenant):
            TenantUser.objects.create(user=user, role=role)
    client.force_login(user)
    assert client.post('/manage/settings/media-backup/', HTTP_HOST=HOST).status_code == 403
    settings_page = client.get('/manage/settings/', HTTP_HOST=HOST)
    assert b'Download media ZIP' not in settings_page.content


def test_media_export_requires_login_and_post_and_csrf(store, client):
    _, owner = store
    assert client.post('/manage/settings/media-backup/', HTTP_HOST=HOST).status_code == 302
    client.force_login(owner)
    assert client.get('/manage/settings/media-backup/', HTTP_HOST=HOST).status_code == 405
    from django.test import Client
    checked = Client(enforce_csrf_checks=True)
    checked.force_login(owner)
    assert checked.post('/manage/settings/media-backup/', HTTP_HOST=HOST).status_code == 403
    assert b'Download media ZIP' in client.get('/manage/settings/', HTTP_HOST=HOST).content


def test_backup_rejects_traversal_in_recorded_image_names(store):
    tenant, _ = store
    with tenant_context(tenant):
        MenuItem.objects.create(name='Bad path', price=100, image='../private.png')
    archive_file, report = build_media_backup(tenant)
    with archive_file, ZipFile(archive_file) as archive:
        assert not any('..' in name for name in archive.namelist())
    assert report['image_count'] == 0 and len(report['missing_files']) == 1


def test_backup_does_not_follow_a_configuration_reference_to_another_stores_private_library(store, settings):
    tenant, _ = store
    other = Tenant.objects.create(slug='another', name='Another')
    path = settings.MEDIA_ROOT / f'website/{other.pk}/private.png'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'other stores private draft')
    config = tenant.config
    config.theme = {'logo_url': f'/media/website/{other.pk}/private.png'}
    config.save()
    archive_file, report = build_media_backup(tenant)
    with archive_file, ZipFile(archive_file) as archive:
        assert not any(name.startswith('media/') for name in archive.namelist())
    assert report['image_count'] == 0
    assert report['missing_files'][0]['reason'] == 'Not owned by this store'
