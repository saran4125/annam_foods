"""The Annam application keeps its data and integrations without SEER screens."""
from copy import deepcopy
from io import BytesIO

import pytest
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from apps.content.models import StorefrontImage
from apps.content.services import default_storefront_design, save_storefront_image, storefront_image_url
from apps.messaging.models import WhatsAppMessage
from apps.orders.models import Order
from apps.tenancy.context import tenant_context, get_current_tenant
from apps.tenancy.models import TenantConfig, TenantSecrets, Tenant
from .test_owner import kitchens, owner, signed_in, catalog, HOST, OTHER


@pytest.mark.parametrize('path', ['/platform/', '/platform/login/', '/platform/about/'])
def test_seer_bookmarks_open_the_only_admin_login(client, kitchens, path):
    response = client.get(path, HTTP_HOST=HOST, follow=True)
    assert response.status_code == 200
    assert response.resolver_match.view_name == 'owner:login'
    assert b'SEER' not in response.content and b'SeerKitchen' not in response.content
    assert b'Log in to manage Annam' in response.content
    assert response.redirect_chain == [('/manage/login/', 302)]


def test_only_admin_login_authenticates_and_returns_directly_to_dashboard(client, owner):
    response = client.post('/manage/login/', {'username': 'owner', 'password': 'pw-for-tests-only'}, HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'] == '/manage/'
    dashboard = client.get(response['Location'], HTTP_HOST=HOST)
    assert dashboard.status_code == 200
    for removed in [b'My kitchens', b'Workspace overview', b'>Domains<', b'>Appearance<', b'SeerKitchen']:
        assert removed not in dashboard.content
    for kept in [b'Orders', b'WhatsApp inbox', b'Offer banners', b'Pages', b'Razorpay payments', b'Checkout settings', b'Billing settings']:
        assert kept in dashboard.content


@pytest.mark.parametrize('path', [
    '/platform/admin/', '/platform/admin/kitchens/new/', '/platform/admin/kitchens/annam/',
    '/platform/workspaces/annam/domains/', '/platform/domains/allow-certificate/',
    '/platform/invitations/accept/', '/.well-known/seerkitchen-domain',
    '/manage/appearance/', '/manage/appearance/render/', '/manage/appearance/upload/',
    '/platform/workspaces/annam/manage/appearance/', '/admin/login/',
])
def test_retired_tools_cannot_be_opened_or_mutated_even_by_superuser(client, kitchens, path):
    user = get_user_model().objects.create_superuser('annam-admin', 'admin@example.test', 'only-test-password')
    client.force_login(user)
    before = deepcopy(TenantConfig.objects.get(tenant=kitchens[0]).storefront_design)
    count = Tenant.objects.count()
    assert client.get(path, HTTP_HOST=HOST).status_code == 404
    response = client.post(path, {'action': 'publish', 'name': 'Unwanted Kitchen'}, HTTP_HOST=HOST)
    assert response.status_code in (404, 405)
    assert Tenant.objects.count() == count
    assert TenantConfig.objects.get(tenant=kitchens[0]).storefront_design == before


@pytest.mark.parametrize(('old', 'new'), [
    ('/platform/workspaces/annam/', '/manage/'),
    ('/platform/workspaces/annam/manage/', '/manage/'),
    ('/platform/workspaces/annam/manage/orders/?status=preparing', '/manage/orders/?status=preparing'),
    ('/platform/workspaces/annam/manage/login/', '/manage/login/'),
    ('/platform/workspaces/annam/billing/', '/billing/'),
    ('/platform/workspaces/annam/billing/login/', '/billing/login/'),
    ('/platform/workspaces/annam/preview/', '/'),
    ('/platform/workspaces/annam/preview/menu/?design=draft', '/menu/'),
])
def test_old_annam_links_redirect_to_local_tools_without_replaying_posts(client, kitchens, old, new):
    response = client.get(old, HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'] == new
    assert client.post(old, {'action': 'place'}, HTTP_HOST=HOST).status_code == 405


@pytest.mark.parametrize('suffix', ['manage/', 'billing/', 'preview/', 'domains/', ''])
def test_bookmarks_cannot_switch_into_another_store(signed_in, suffix):
    assert signed_in.get('/platform/workspaces/rival/' + suffix, HTTP_HOST=HOST).status_code == 404
    assert get_current_tenant() is None


@pytest.mark.parametrize('suffix', ['preview//evil.example/', 'preview/%2f/evil.example/', 'manage/../admin/', 'preview/%5cevil.example/'])
def test_bookmark_translation_rejects_external_and_traversal_destinations(client, kitchens, suffix):
    assert client.get('/platform/workspaces/annam/' + suffix, HTTP_HOST=HOST).status_code == 404


def test_old_login_next_is_translated_but_external_next_is_not_used(client, kitchens):
    response = client.get('/platform/login/', {'next': '/platform/workspaces/annam/manage/orders/'}, HTTP_HOST=HOST)
    assert response['Location'] == '/manage/login/?next=%2Fmanage%2Forders%2F'
    response = client.get('/platform/login/', {'next': 'https://evil.example/'}, HTTP_HOST=HOST)
    assert response['Location'] == '/manage/login/'
    response = client.post('/platform/login/', {'username': 'owner', 'password': 'pw-for-tests-only'}, HTTP_HOST=HOST)
    assert response.status_code == 405 and '_auth_user_id' not in client.session


def test_billing_remains_separate_and_store_settings_have_no_editor_links(client, signed_in, owner):
    response = Client().get('/billing/', HTTP_HOST=HOST)
    assert response.status_code == 302 and response['Location'].startswith('/billing/login/')
    page = signed_in.get('/billing/', HTTP_HOST=HOST)
    assert page.status_code == 200 and b'My kitchens' not in page.content
    page = signed_in.get('/manage/settings/', HTTP_HOST=HOST)
    assert page.status_code == 200 and b'Appearance' not in page.content
    assert signed_in.post('/manage/logout/', HTTP_HOST=HOST)['Location'] == '/manage/login/'


def test_published_text_footer_and_photos_survive_removal_and_drafts_stay_hidden(client, kitchens, owner, settings, tmp_path):
    tenant = kitchens[0]
    out = BytesIO()
    Image.new('RGB', (16, 16), '#eeaa55').save(out, 'PNG')
    with tenant_context(tenant):
        image = save_storefront_image(tenant, SimpleUploadedFile('annam.png', out.getvalue(), content_type='image/png'))
        url = storefront_image_url(tenant, image)
        design = default_storefront_design(tenant.config)
        design['images'] = {'hero': url, 'logo': url, 'closing_1': url, 'closing_2': url, 'closing_3': url}
        design['content'] = {'hero.title': 'Saved Annam headline', 'story.body': 'Our saved Annam story',
                             'footer.address': 'Our saved Chennai address', 'footer.email': 'saved@example.test'}
        draft = deepcopy(design)
        draft['content']['story.body'] = 'UNPUBLISHED DRAFT MUST STAY PRIVATE'
        state = {'published': design, 'draft': draft, 'previous': design, 'revision': 7}
        TenantConfig.objects.filter(tenant=tenant).update(storefront_design=state)
    settings.MEDIA_ROOT = tmp_path / 'missing-media'
    client.force_login(owner)
    for query in ('', '?design=draft'):
        page = client.get('/' + query, HTTP_HOST=HOST)
        assert page.status_code == 200
        assert b'Our saved Annam story' in page.content and b'Our saved Chennai address' in page.content
        assert b'saved@example.test' in page.content and url.encode() in page.content
        assert b'UNPUBLISHED DRAFT' not in page.content
        assert b'Draft preview' not in page.content and b'Back to Appearance' not in page.content
    client.logout()
    response = client.get(url, HTTP_HOST=HOST)
    assert response.status_code == 200 and response['Content-Type'] == 'image/png'
    assert b''.join(response.streaming_content) == out.getvalue()
    assert TenantConfig.objects.get(tenant=tenant).storefront_design == state
    assert not Order.all_tenants.exists()


def test_draft_only_images_remain_private_without_editor(client, kitchens):
    tenant = kitchens[0]
    with tenant_context(tenant):
        image = StorefrontImage.objects.create(name='private.png', data=b'private', content_type='image/png', width=1, height=1)
        url = storefront_image_url(tenant, image)
    assert client.get(url, HTTP_HOST=HOST).status_code == 404


def test_single_store_deployment_rejects_other_store_hosts_and_callback_slugs(client, kitchens, settings):
    settings.STORE_SLUG = 'annam'
    assert client.get('/', HTTP_HOST=HOST).status_code == 200
    assert client.get('/', HTTP_HOST=OTHER).status_code == 404
    assert client.get('/manage/login/', HTTP_HOST=OTHER).status_code == 404
    assert client.get('/healthz', HTTP_HOST='health.test').status_code == 200
    assert client.post('/platform/webhooks/rival/whatsapp/n8n/', '{}', content_type='application/json', HTTP_HOST=HOST).status_code == 404
    assert client.post('/platform/webhooks/rival/razorpay/test/', '{}', content_type='application/json', HTTP_HOST=HOST).status_code == 404


def test_existing_n8n_callback_keeps_authentication_and_deduplication(client, kitchens):
    connection = TenantSecrets.objects.create(tenant=kitchens[0], wa_phone_number_id='12345')
    token = 'annam-sync-test-token-not-a-real-secret'
    connection.wa_sync_token = token
    connection.save()
    data = {'event': 'outbound', 'phone_number_id': '12345', 'message_id': 'wamid.annam-existing',
            'message': {'to': '919999999999', 'type': 'text', 'text': {'body': 'Existing n8n reply'}}}
    url = '/platform/webhooks/annam/whatsapp/n8n/'
    assert client.post(url, data, content_type='application/json', HTTP_HOST=HOST).status_code == 403
    for _ in range(2):
        assert client.post(url, data, content_type='application/json', HTTP_HOST=HOST,
                           HTTP_AUTHORIZATION='Bearer ' + token).status_code == 200
    with tenant_context(kitchens[0]):
        assert WhatsAppMessage.objects.count() == 1
        assert WhatsAppMessage.objects.get().body == 'Existing n8n reply'


def test_scheduled_business_day_work_ignores_historical_other_stores(kitchens, settings):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from apps.jobs.services import run_daily_handoff
    settings.STORE_SLUG = 'annam'
    runs = run_daily_handoff(datetime(2026, 10, 22, 12, tzinfo=ZoneInfo('Asia/Kolkata')))
    assert [pk for pk, day in runs] == [kitchens[0].pk]


def test_old_platform_host_has_no_login_but_keeps_verified_callback_routes(client, kitchens, settings):
    settings.STORE_SLUG = 'annam'
    for path in ['/', '/platform/login/', '/admin/login/']:
        assert client.get(path, HTTP_HOST='admin.localhost').status_code == 404
    connection = TenantSecrets.objects.create(tenant=kitchens[0], wa_phone_number_id='12345')
    connection.wa_sync_token = 'legacy-host-test-token-not-a-real-secret'
    connection.save()
    # Reaching the authentication failure proves the stable callback resolves.
    assert client.post('/platform/webhooks/annam/whatsapp/n8n/', {}, content_type='application/json',
                       HTTP_HOST='admin.localhost').status_code == 403
    assert client.post('/platform/webhooks/rival/whatsapp/n8n/', {}, content_type='application/json',
                       HTTP_HOST='admin.localhost').status_code == 404
