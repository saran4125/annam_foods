"""Visual copy/photo edits are drafts until published, with tenant-safe uploads."""
import io
from copy import deepcopy

import pytest
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.content.models import StorefrontImage
from apps.content.services import default_storefront_design, validate_storefront_design
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantConfig, TenantUser
from .test_appearance import kitchens, owner, payload, HOST, OTHER


def photo(name='kitchen.png'):
    out = io.BytesIO()
    Image.new('RGB', (24, 24), '#eeaa55').save(out, format='PNG')
    return SimpleUploadedFile(name, out.getvalue(), content_type='image/png')


def test_visual_canvas_renders_unsaved_copy_without_publishing_or_saving(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data['copy_hero.title'] = 'Our fresh new kitchen headline'
    response = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b'data-canvas-text="hero.title"' in response.content
    assert b'Our fresh new kitchen headline' in response.content
    assert b'js/storefront-canvas.js' in response.content
    assert b'js/storefront.js' not in response.content
    assert 'no-store' in response['Cache-Control']
    assert not TenantConfig.objects.get(tenant=kitchens[0]).storefront_design
    public = client.get('/', HTTP_HOST=HOST)
    assert b'Our fresh new kitchen headline' not in public.content
    assert b'js/storefront-canvas.js' not in public.content


def test_canvas_copy_is_plain_text_not_executable_html(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data['copy_hero.title'] = '<img src=x onerror=alert(1)>'
    response = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert b'&lt;img src=x onerror=alert(1)&gt;' in response.content
    assert b'<img src=x onerror=alert(1)>' not in response.content


def test_visual_text_saves_as_a_private_draft_then_publishes_and_restores(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data.update({'copy_hero.title': 'Cooked in our home', 'copy_story.body': 'Our family kitchen story'})
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    assert b'Cooked in our home' not in client.get('/', HTTP_HOST=HOST).content
    assert b'Cooked in our home' in client.get('/?design=draft', HTTP_HOST=HOST).content
    data.update(action='publish', revision=1)
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    client.logout()
    response = client.get('/', HTTP_HOST=HOST)
    assert b'Cooked' in response.content and b'Our family kitchen story' in response.content
    client.force_login(owner)
    assert client.post('/manage/appearance/', {'action': 'restore', 'revision': 2}, HTTP_HOST=HOST).status_code == 302
    assert b'Our family kitchen story' not in client.get('/', HTTP_HOST=HOST).content


def test_draft_photos_are_private_and_survive_a_missing_media_directory(client, kitchens, owner, settings, tmp_path):
    client.force_login(owner)
    response = client.post('/manage/appearance/upload/', {'image': photo()}, HTTP_HOST=HOST)
    assert response.status_code == 201
    url = response.json()['url']
    settings.MEDIA_ROOT = tmp_path / 'empty-media-after-restart'
    image = client.get(url, HTTP_HOST=HOST)
    assert image.status_code == 200 and image['Content-Type'] == 'image/png'
    assert 'no-store' in image['Cache-Control']
    assert b''.join(image.streaming_content).startswith(b'\x89PNG')
    client.logout()
    assert client.get(url, HTTP_HOST=HOST).status_code == 404
    client.force_login(owner)
    data = payload(kitchens[0].config, action='publish')
    data['image_hero'] = url
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    client.logout()
    assert client.get(url, HTTP_HOST=HOST).status_code == 200
    assert url.encode() in client.get('/', HTTP_HOST=HOST).content


def test_one_kitchen_cannot_use_or_preview_another_kitchens_private_photo(client, kitchens, owner):
    client.force_login(owner)
    url = client.post('/manage/appearance/upload/', {'image': photo()}, HTTP_HOST=HOST).json()['url']
    rival = get_user_model().objects.create_user(username='rival-designer')
    TenantUser.all_tenants.create(tenant=kitchens[1], user=rival, role='owner')
    client.force_login(rival)
    assert client.get(url, HTTP_HOST=OTHER).status_code == 404
    data = payload(kitchens[1].config, action='publish')
    data['image_hero'] = url
    response = client.post('/manage/appearance/', data, HTTP_HOST=OTHER)
    assert response.status_code == 200 and b'different kitchen' in response.content
    response = client.post('/manage/appearance/render/', data, HTTP_HOST=OTHER)
    assert response.status_code == 400
    assert not TenantConfig.objects.get(tenant=kitchens[1]).storefront_design


@pytest.mark.parametrize('file', [
    SimpleUploadedFile('bad.svg', b'<svg onload="alert(1)"></svg>', content_type='image/svg+xml'),
    SimpleUploadedFile('large.png', b'x' * (3 * 1024 * 1024 + 1), content_type='image/png'),
])
def test_upload_rejects_active_content_and_oversized_files(client, kitchens, owner, file):
    client.force_login(owner)
    response = client.post('/manage/appearance/upload/', {'image': file}, HTTP_HOST=HOST)
    assert response.status_code == 400
    with tenant_context(kitchens[0]):
        assert StorefrontImage.objects.count() == 0


def test_visual_render_and_upload_require_csrf_and_kitchen_access(client, kitchens, owner):
    secured = Client(enforce_csrf_checks=True)
    secured.force_login(owner)
    assert secured.post('/manage/appearance/render/', payload(kitchens[0].config), HTTP_HOST=HOST).status_code == 403
    assert secured.post('/manage/appearance/upload/', {'image': photo()}, HTTP_HOST=HOST).status_code == 403
    client.force_login(owner)
    assert client.post('/manage/appearance/render/', payload(kitchens[1].config), HTTP_HOST=OTHER).status_code == 403
    assert client.post('/manage/appearance/upload/', {'image': photo()}, HTTP_HOST=OTHER).status_code == 403


def test_unknown_content_fields_and_overlong_copy_cannot_enter_a_design(kitchens):
    design = default_storefront_design(kitchens[0].config)
    design['content'] = {'checkout.total': '1'}
    with pytest.raises(ValidationError):
        validate_storefront_design(design)
    design['content'] = {'hero.title': 'x' * 161}
    with pytest.raises(ValidationError):
        validate_storefront_design(design)


def test_logo_and_website_name_can_be_changed_without_changing_the_legal_business_name(client, kitchens, owner):
    client.force_login(owner)
    url = client.post('/manage/appearance/upload/', {'image': photo('logo.png')}, HTTP_HOST=HOST).json()['url']
    data = payload(kitchens[0].config, action='publish')
    data.update({'copy_brand.name': 'Our Family Kitchen', 'image_logo': url})
    response = client.post('/manage/appearance/', data, HTTP_HOST=HOST)
    assert response.status_code == 302
    public = client.get('/', HTTP_HOST=HOST)
    assert b'Our Family Kitchen' in public.content
    assert public.context['storefront_theme']['logo_url'] == url
    kitchens[0].refresh_from_db()
    assert kitchens[0].name == 'appearance'


def test_render_rejects_missing_photo_references_instead_of_showing_a_broken_draft(client, kitchens, owner):
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data['image_hero'] = '/platform/assets/appearance/00000000-0000-0000-0000-000000000000/'
    response = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert response.status_code == 400
    assert 'no longer available' in str(response.json())


def test_canvas_render_does_not_change_product_prices_or_create_orders(client, kitchens, owner):
    from decimal import Decimal
    from apps.catalog.models import MenuItem
    from apps.orders.models import Order
    with tenant_context(kitchens[0]):
        item = MenuItem.objects.create(name='Meals', price=Decimal('120'))
    client.force_login(owner)
    data = payload(kitchens[0].config)
    data['copy_hero.title'] = 'Fresh food from our kitchen'
    data['price'] = '1'
    response = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert response.status_code == 200
    with tenant_context(kitchens[0]):
        item.refresh_from_db()
        assert item.price == Decimal('120')
        assert Order.objects.count() == 0
