from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
import hashlib
import json
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST, OTHER, catalog
from apps.tenancy.context import tenant_context, get_current_tenant
from apps.tenancy.models import Tenant, TenantDomain, TenantUser, TenantConfig, OwnerInvitation, PlatformAuditEvent, TenantSecrets
from apps.platform_portal.services import provision_kitchen, invite_owner, accept_invitation, invitation_for_token, change_kitchen_status


@pytest.fixture
def operator(db):
    return get_user_model().objects.create_superuser("platform-operator", "operator@example.test", "Only-for-tests-928!")


@pytest.fixture
def admin_client(client, operator, kitchens):
    client.force_login(operator)
    return client


def create_data(**overrides):
    return {"name":"Second Kitchen", "slug":"second-kitchen", "owner_email":"new-owner@example.test", "preset":"daily-meals", **overrides}


def test_central_login_routes_existing_owner_to_their_workspace(client, owner, kitchens):
    response=client.post("/platform/login/",{"username":"owner","password":"pw-for-tests-only"},HTTP_HOST=HOST)
    assert response.status_code==302 and response["Location"]=="/platform/workspaces/annam/manage/"
    assert client.get(response["Location"],HTTP_HOST=HOST).status_code==200
    assert client.get("/",HTTP_HOST=HOST).status_code==200


def test_central_platform_requires_auth_and_does_not_change_unknown_host_policy(client, kitchens):
    assert client.get("/platform/",HTTP_HOST=HOST).status_code==302
    assert client.get("/platform/",HTTP_HOST="unknown.example").status_code==404
    assert client.get("/",HTTP_HOST="admin.localhost").status_code==200
    assert client.get("/admin/login/",HTTP_HOST=HOST).status_code==404


def test_platform_administration_requires_superuser_not_ordinary_owner(signed_in):
    for path in ("/platform/admin/","/platform/admin/kitchens/new/","/platform/admin/kitchens/annam/"):
        assert signed_in.get(path,HTTP_HOST=HOST).status_code==403
        assert signed_in.post(path,create_data(),HTTP_HOST=HOST).status_code==403


def test_owner_only_sees_their_kitchens_and_workspace_urls_cannot_cross_tenants(signed_in, kitchens, catalog):
    page=signed_in.get("/platform/",HTTP_HOST=HOST)
    assert b'Annam' in page.content and b'Rival' not in page.content
    for path in ("/platform/workspaces/rival/","/platform/workspaces/rival/manage/","/platform/workspaces/rival/billing/","/platform/workspaces/rival/preview/"):
        assert signed_in.get(path,HTTP_HOST=HOST).status_code==404
    page=signed_in.get("/platform/workspaces/annam/manage/dishes/",HTTP_HOST=HOST)
    assert page.status_code==200
    assert b'Ellu Podi' in page.content and b'Rival Roll' not in page.content
    assert b'/platform/workspaces/annam/manage/dishes/' in page.content
    assert b'/platform/workspaces/annam/preview/' in page.content
    assert get_current_tenant() is None
    assert signed_in.post(f'/platform/workspaces/annam/manage/dishes/{catalog["theirs"].pk}/toggle/',HTTP_HOST=HOST).status_code==404


def test_workspace_tools_reverse_links_and_redirects_inside_selected_kitchen(admin_client, kitchens, catalog):
    root='/platform/workspaces/rival/'
    for suffix in ('manage/','manage/settings/','billing/','billing/new/','billing/settings/','manage/whatsapp/','manage/whatsapp/settings/','preview/','preview/menu/'):
        page=admin_client.get(root+suffix,HTTP_HOST=HOST)
        assert page.status_code==200,(suffix,page.status_code)
    page=admin_client.get(root+'manage/whatsapp/settings/',HTTP_HOST=HOST)
    assert b'/platform/webhooks/rival/whatsapp/n8n/' in page.content
    page=admin_client.get(root+'billing/new/',HTTP_HOST=HOST)
    assert b'Rival Roll' in page.content and b'Ellu Podi' not in page.content
    page=admin_client.post(root+'manage/dishes/'+str(catalog['theirs'].pk)+'/toggle/',HTTP_HOST=HOST)
    assert page.status_code==302 and page['Location'].startswith(root+'manage/')
    assert admin_client.get('/manage/',HTTP_HOST=HOST).wsgi_request.tenant.pk==kitchens[0].pk


def test_provisioning_creates_presets_owner_and_private_workspace_without_live_credentials(admin_client, operator, settings):
    settings.TENANT_BASE_DOMAIN='localhost'
    response=admin_client.post('/platform/admin/kitchens/new/',create_data(),HTTP_HOST=HOST)
    assert response.status_code==200 and response.context['invitation_url']
    kitchen=Tenant.objects.get(slug='second-kitchen')
    assert kitchen.status=='provisioning' and kitchen.primary_domain=='second-kitchen.localhost'
    assert TenantDomain.objects.get(hostname='second-kitchen.localhost').tenant_id==kitchen.pk
    assert admin_client.get('/platform/workspaces/second-kitchen/manage/',HTTP_HOST=HOST).status_code==200
    assert admin_client.get('/',HTTP_HOST='second-kitchen.localhost').status_code==200
    from apps.catalog.models import Slot
    with tenant_context(kitchen):
        assert Slot.objects.count()==3
        member=TenantUser.objects.get()
        assert member.role=='owner' and not member.user.has_usable_password()
        assert PlatformAuditEvent.objects.filter(action='kitchen_created').exists()
    assert not TenantSecrets.objects.filter(tenant=kitchen).exists()
    token=parse_qs(urlsplit(response.context['invitation_url']).query)['token'][0]
    assert not OwnerInvitation.all_tenants.filter(token_hash=token).exists()
    assert OwnerInvitation.all_tenants.get(tenant=kitchen).token_hash==hashlib.sha256(token.encode()).hexdigest()


def test_no_base_domain_still_provides_private_website_preview(admin_client, settings):
    settings.TENANT_BASE_DOMAIN=''
    response=admin_client.post('/platform/admin/kitchens/new/',create_data(),HTTP_HOST=HOST)
    assert response.status_code==200
    kitchen=Tenant.objects.get(slug='second-kitchen')
    assert not kitchen.primary_domain and not kitchen.domains.exists()
    assert admin_client.get('/platform/workspaces/second-kitchen/preview/',HTTP_HOST=HOST).status_code==200


def test_invalid_duplicate_and_reserved_addresses_do_not_create_accounts_or_kitchens(admin_client, kitchens):
    for slug in ('admin','two--hyphens','annam'):
        response=admin_client.post('/platform/admin/kitchens/new/',create_data(slug=slug),HTTP_HOST=HOST)
        assert response.status_code==200 and response.context['form'].errors
    assert Tenant.objects.count()==2
    assert not get_user_model().objects.filter(username='new-owner@example.test').exists()


def test_new_owner_activation_sets_password_once_and_opens_only_their_kitchen(operator, kitchens):
    kitchen, invitation, token=provision_kitchen(actor=operator,**create_data())
    browser=Client()
    page=browser.get('/platform/invitations/accept/',{'token':token},HTTP_HOST=HOST)
    assert page.status_code==200 and page['Cache-Control'].find('no-store')>=0
    weak=browser.post('/platform/invitations/accept/',{'token':token,'new_password1':'123','new_password2':'123'},HTTP_HOST=HOST)
    assert weak.status_code==200 and weak.context['form'].errors
    response=browser.post('/platform/invitations/accept/',{'token':token,'new_password1':'Strong-test-password-8x4!','new_password2':'Strong-test-password-8x4!'},HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']=='/platform/workspaces/second-kitchen/'
    assert browser.get(response['Location'],HTTP_HOST=HOST).status_code==200
    assert browser.get('/platform/workspaces/annam/manage/',HTTP_HOST=HOST).status_code==404
    assert invitation_for_token(token) is None
    invitation.user.refresh_from_db();assert invitation.user.check_password('Strong-test-password-8x4!')


def test_existing_account_invitation_never_changes_password_or_bypasses_login(operator, owner, kitchens):
    owner.email='known-owner@example.test';owner.save()
    invitation, token=invite_owner(actor=operator,tenant=kitchens[1],email=owner.email,role='manager')
    anonymous=Client()
    response=anonymous.post('/platform/invitations/accept/',{'token':token},HTTP_HOST=HOST)
    assert response.status_code==200
    owner.refresh_from_db();assert owner.check_password('pw-for-tests-only')
    assert invitation_for_token(token) is not None
    anonymous.force_login(owner)
    response=anonymous.post('/platform/invitations/accept/',{'token':token},HTTP_HOST=HOST)
    assert response.status_code==302
    with tenant_context(kitchens[1]):
        assert TenantUser.objects.get(user=owner).role=='manager'


def test_reissuing_revokes_old_links_and_expired_invites_are_rejected(operator, kitchens):
    invitation, token=invite_owner(actor=operator,tenant=kitchens[0],email='invitee@example.test')
    second, token2=invite_owner(actor=operator,tenant=kitchens[0],email='invitee@example.test')
    assert invitation_for_token(token) is None
    assert invitation_for_token(token2).pk==second.pk
    OwnerInvitation.all_tenants.filter(pk=second.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    with pytest.raises(Exception,match='expired'):
        accept_invitation(token=token2,password='Strong-test-password-8x4!')


def test_status_changes_and_feature_settings_are_superuser_only_and_audited(admin_client, signed_in, operator, kitchens):
    browser=Client();browser.force_login(operator)
    response=browser.post('/platform/admin/kitchens/annam/',{'action':'status','status':'suspended'},HTTP_HOST=HOST)
    assert response.status_code==302
    kitchens[0].refresh_from_db();assert not kitchens[0].can_take_orders
    assert browser.post('/platform/admin/kitchens/annam/',{'action':'features','snacks_courier':'on'},HTTP_HOST=HOST).status_code==302
    with tenant_context(kitchens[0]):
        config=TenantConfig.objects.get(tenant=kitchens[0])
        assert config.features['snacks_courier'] is True and config.features['website_ordering'] is False
        assert PlatformAuditEvent.objects.filter(action='status_changed').exists()
        assert PlatformAuditEvent.objects.filter(action='website_features_updated').exists()


def test_login_cannot_redirect_to_external_sites(client, owner):
    response=client.post('/platform/login/?next=https://evil.example/',{'username':'owner','password':'pw-for-tests-only'},HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']=='/platform/workspaces/annam/manage/'


def test_scoped_n8n_webhook_cannot_write_into_the_hostname_tenant(client, kitchens):
    secret=TenantSecrets.objects.create(tenant=kitchens[1],wa_phone_number_id='555')
    secret.wa_sync_token='test-sync-token-for-rival-123';secret.save()
    data={'event':'outbound','phone_number_id':'555','message_id':'wamid.workspace','message':{'to':'919999999999','type':'text','text':{'body':'Rival message'}}}
    url='/platform/webhooks/rival/whatsapp/n8n/'
    assert client.post(url,json.dumps(data),content_type='application/json',HTTP_HOST=HOST).status_code==403
    assert client.post(url,json.dumps(data),content_type='application/json',HTTP_HOST=HOST,HTTP_AUTHORIZATION='Bearer test-sync-token-for-rival-123').status_code==200
    from apps.messaging.models import WhatsAppMessage
    with tenant_context(kitchens[1]):assert WhatsAppMessage.objects.get().body=='Rival message'
    with tenant_context(kitchens[0]):assert not WhatsAppMessage.objects.exists()


def test_preview_links_keep_the_selected_kitchen_without_changing_public_storefront(signed_in, kitchens):
    from apps.content.models import Banner
    with tenant_context(kitchens[0]):
        Banner.objects.create(title='Preview offer',image='banners/test.jpg',link='/menu/')
    private=signed_in.get('/platform/workspaces/annam/preview/',HTTP_HOST=HOST)
    public=signed_in.get('/',HTTP_HOST=HOST)
    assert b'/platform/workspaces/annam/preview/menu/' in private.content
    assert b'href="/menu/"' in public.content
    assert b'/platform/workspaces/' not in public.content


def test_platform_forms_reject_cross_site_posts(operator, kitchens):
    strict=Client(enforce_csrf_checks=True);strict.force_login(operator)
    assert strict.post('/platform/admin/kitchens/new/',create_data(),HTTP_HOST=HOST).status_code==403
    assert strict.post('/platform/admin/kitchens/annam/',{'action':'status','status':'suspended'},HTTP_HOST=HOST).status_code==403


def test_invitation_forms_preserve_same_origin_csrf_and_hide_cross_origin_referrers(operator, kitchens):
    _, invitation, token = provision_kitchen(actor=operator, **create_data())
    strict = Client(enforce_csrf_checks=True)
    page = strict.get('/platform/invitations/accept/', {'token': token}, HTTP_HOST=HOST)
    assert page['Referrer-Policy'] == 'same-origin'
    response = strict.post('/platform/invitations/accept/', {
        'token': token, 'new_password1': 'Strong-owner-password-x7!',
        'new_password2': 'Strong-owner-password-x7!',
        'csrfmiddlewaretoken': strict.cookies['csrftoken'].value,
    }, HTTP_HOST=HOST, HTTP_ORIGIN='http://' + HOST)
    assert response.status_code == 302
    invitation.refresh_from_db()
    assert invitation.accepted_at is not None


def test_long_owner_email_returns_validation_error_without_partial_setup(admin_client):
    email = 'a' * 64 + '@' + 'b' * 60 + '.' + 'c' * 30 + '.com'
    response = admin_client.post('/platform/admin/kitchens/new/', create_data(owner_email=email), HTTP_HOST=HOST)
    assert response.status_code == 200 and response.context['form'].errors
    assert not Tenant.objects.filter(slug='second-kitchen').exists()
    assert not get_user_model().objects.filter(email=email).exists()


def test_failed_preset_rolls_back_new_tenant_and_new_owner(operator):
    from unittest.mock import patch
    with patch('apps.platform_portal.services.apply_preset',side_effect=RuntimeError('preset failed')):
        with pytest.raises(RuntimeError):
            provision_kitchen(actor=operator,**create_data())
    assert not Tenant.objects.filter(slug='second-kitchen').exists()
    assert not get_user_model().objects.filter(username='new-owner@example.test').exists()
    assert not OwnerInvitation.all_tenants.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_invitation_acceptance_sets_one_password_only(operator):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import connections
    kitchen, invitation, token=provision_kitchen(actor=operator,**create_data())
    passwords=['First-strong-password-x7!','Second-strong-password-z8!']
    def accept(password):
        try:
            accept_invitation(token=token,password=password)
            return password
        except ValidationError:
            return None
        finally:
            connections.close_all()
    from django.core.exceptions import ValidationError
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(accept,passwords))
    accepted=[result for result in results if result]
    assert len(accepted)==1
    user=get_user_model().objects.get(pk=invitation.user_id)
    assert user.check_password(accepted[0])
