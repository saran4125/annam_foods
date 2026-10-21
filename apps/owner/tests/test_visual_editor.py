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


def test_closing_photos_can_be_saved_published_and_reset_independently(client, kitchens, owner):
    import re

    def closing_sources(response):
        closing = response.content.decode().split('class="closing"', 1)[1].split('</section>', 1)[0]
        return re.findall(r'<img src="([^"]+)"', closing)

    client.force_login(owner)
    urls = [client.post('/manage/appearance/upload/', {'image': photo(f'{position}.png')},
                        HTTP_HOST=HOST).json()['url'] for position in ['left', 'middle', 'right']]
    data = payload(kitchens[0].config)
    data.update({f'image_closing_{index}': url for index, url in enumerate(urls, 1)})
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    assert closing_sources(client.get('/', HTTP_HOST=HOST)) == []
    canvas = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert canvas.status_code == 200
    assert closing_sources(canvas) == urls
    for index in range(1, 4):
        assert f'data-canvas-image="closing_{index}"'.encode() in canvas.content
    data.update(action='publish', revision=1)
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    client.logout()
    assert closing_sources(client.get('/', HTTP_HOST=HOST)) == urls
    assert all(client.get(url, HTTP_HOST=HOST).status_code == 200 for url in urls)
    client.force_login(owner)
    data.update(image_closing_2='', revision=2)
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    assert closing_sources(client.get('/', HTTP_HOST=HOST)) == [urls[0], urls[2]]
    assert client.post('/manage/appearance/', {'action': 'restore', 'revision': 3}, HTTP_HOST=HOST).status_code == 302
    assert closing_sources(client.get('/', HTTP_HOST=HOST)) == urls


def test_closing_keeps_original_menu_photos_and_offers_empty_editor_slots():
    from types import SimpleNamespace
    from django.template import Context
    from apps.storefront.templatetags.storefront_extras import closing_photos

    picks = [SimpleNamespace(image=SimpleNamespace(url=f'/media/{i}.jpg')) for i in range(3)]
    assert [slot['url'] for slot in closing_photos(Context({'hero_picks': picks}))] == [p.image.url for p in picks]
    slots = closing_photos(Context({'hero_picks': picks, 'storefront_images': {'closing_2': '/replacement/'}}))
    assert [slot['url'] for slot in slots] == ['/media/0.jpg', '/replacement/', '/media/2.jpg']
    assert closing_photos(Context({'hero_picks': picks[:1]})) == []
    empty = closing_photos(Context({'appearance_canvas': True}))
    assert [slot['key'] for slot in empty] == ['closing_1', 'closing_2', 'closing_3']
    assert all(not slot['url'] for slot in empty)


def test_footer_details_are_private_until_published_and_update_contact_links(client, kitchens, owner):
    from apps.tenancy.models import BillingProfile
    config = kitchens[0].config
    config.support_phone = '+91 95510 79550'
    config.tagline = 'Original kitchen description'
    config.theme = {'contact_email': 'original@example.test'}
    config.save()
    billing, _ = BillingProfile.objects.get_or_create(tenant=kitchens[0])
    billing.address = 'Original billing address'
    billing.fssai_no = '12345678901234'
    billing.save()
    client.force_login(owner)
    data = payload(config)
    data.update({
        'copy_footer.description': 'Freshly cooked in our family kitchen',
        'copy_footer.phone': '+91 98765 43210',
        'copy_footer.email': 'hello@example.test',
        'copy_footer.address': '42 Kitchen Road\nChennai 600005',
        'copy_footer.whatsapp': '+91 91234 56789',
        'copy_footer.fssai': '98765432109876',
        'copy_footer.whatsapp_cta': 'Message our kitchen',
    })
    canvas = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert canvas.status_code == 200
    for key in ('description', 'phone', 'email', 'address', 'fssai'):
        assert f'data-canvas-text="footer.{key}"'.encode() in canvas.content
    assert b'href="tel:+91 98765 43210"' in canvas.content
    assert b'href="mailto:hello@example.test"' in canvas.content
    assert b'https://wa.me/919123456789' in canvas.content
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    public = client.get('/', HTTP_HOST=HOST)
    assert b'hello@example.test' not in public.content
    assert b'Original billing address' in public.content
    assert b'hello@example.test' in client.get('/?design=draft', HTTP_HOST=HOST).content
    data.update(action='publish', revision=1)
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    client.logout()
    public = client.get('/', HTTP_HOST=HOST)
    assert b'hello@example.test' in public.content
    assert b'Message our kitchen' in public.content
    assert b'href="tel:+91 98765 43210"' in public.content
    assert b'https://wa.me/919123456789' in public.content
    assert b'data-canvas-text=' not in public.content
    assert b'hello@example.test' not in client.get('/', HTTP_HOST=OTHER).content
    config.refresh_from_db()
    billing.refresh_from_db()
    assert config.support_phone == '+91 95510 79550'
    assert billing.address == 'Original billing address'
    assert billing.fssai_no == '12345678901234'
    client.force_login(owner)
    assert client.post('/manage/appearance/', {'action': 'restore', 'revision': 2}, HTTP_HOST=HOST).status_code == 302
    assert b'Original billing address' in client.get('/', HTTP_HOST=HOST).content


@pytest.mark.parametrize('key,value', [
    ('footer.email', 'not-an-email'),
    ('footer.email', 'owner@example.test?subject=Injected'),
    ('footer.phone', 'javascript:alert(1)'),
    ('footer.phone', '123'),
    ('footer.whatsapp', 'https://other.example/'),
    ('footer.fssai', '1234'),
])
def test_footer_rejects_invalid_contact_values_in_both_render_and_publish(client, kitchens, owner, key, value):
    client.force_login(owner)
    data = payload(kitchens[0].config, action='publish')
    data['copy_' + key] = value
    assert client.post('/manage/appearance/render/', data, HTTP_HOST=HOST).status_code == 400
    response = client.post('/manage/appearance/', data, HTTP_HOST=HOST)
    assert response.status_code == 200
    assert response.context['form'].errors
    assert not TenantConfig.objects.get(tenant=kitchens[0]).storefront_design


def test_footer_blank_details_hide_public_contacts_but_remain_editable_in_canvas(client, kitchens, owner):
    config = kitchens[0].config
    config.support_phone = '+91 95510 79550'
    config.save()
    client.force_login(owner)
    data = payload(config, action='publish')
    data.update({f'copy_footer.{key}': '' for key in ('description', 'phone', 'email', 'address', 'whatsapp', 'fssai')})
    canvas = client.post('/manage/appearance/render/', data, HTTP_HOST=HOST)
    assert canvas.status_code == 200 and b'data-canvas-text="footer.phone"' in canvas.content
    assert client.post('/manage/appearance/', data, HTTP_HOST=HOST).status_code == 302
    public = client.get('/', HTTP_HOST=HOST)
    footer = public.content.split(b'<footer', 1)[1].split(b'</footer>', 1)[0]
    assert b'tel:' not in footer and b'mailto:' not in footer and b'wa.me' not in footer
    assert b'FSSAI Lic.' not in footer
