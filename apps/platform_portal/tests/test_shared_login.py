from urllib.parse import parse_qs, urlsplit
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST, OTHER
from apps.platform_portal.tests.test_platform import operator
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantUser


def credentials(**extra):
    return {'username':'owner','password':'pw-for-tests-only',**extra}


def test_superuser_shared_login_opens_platform_administration(client,operator,kitchens):
    response=client.post('/platform/login/',{'username':operator.username,'password':'Only-for-tests-928!'},HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']=='/platform/admin/'
    assert client.get(response['Location'],HTTP_HOST=HOST).status_code==200


@pytest.mark.parametrize('role',['owner','manager','staff'])
def test_shared_login_opens_assigned_admin_for_each_kitchen_role(client,owner,kitchens,role):
    with tenant_context(kitchens[0]):TenantUser.objects.filter(user=owner).update(role=role)
    response=client.post('/platform/login/',credentials(),HTTP_HOST=OTHER)
    assert response.status_code==302 and response['Location']=='/platform/workspaces/annam/manage/'
    assert client.get(response['Location'],HTTP_HOST=OTHER).status_code==200


def test_multiple_memberships_show_picker_with_direct_admin_links(client,owner,kitchens):
    with tenant_context(kitchens[1]):TenantUser.objects.create(user=owner,role='manager')
    response=client.post('/platform/login/',credentials(),HTTP_HOST=HOST)
    assert response['Location']=='/platform/'
    page=client.get(response['Location'],HTTP_HOST=HOST)
    assert b'/platform/workspaces/annam/manage/' in page.content
    assert b'/platform/workspaces/rival/manage/' in page.content


@pytest.mark.parametrize('target',[
    '/platform/admin/','/platform/admin','/platform/workspaces/rival/manage/',
    '/platform/workspaces/annam/manage/login/','/platform/login/',
    '/platform/logout/','https://evil.example/','//evil.example/',
])
def test_saved_target_cannot_override_account_permissions_or_loop_to_login(client,owner,target):
    response=client.post('/platform/login/',credentials(next=target),HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']=='/platform/workspaces/annam/manage/'


def test_kitchen_and_platform_urls_show_their_own_login_pages(client,kitchens):
    local=client.get('/manage/login/',HTTP_HOST=HOST)
    assert local.status_code==200 and local.resolver_match.view_name=='owner:login'
    assert b'Log in to manage Annam' in local.content
    assert b'SEER platform login' in local.content
    central=client.get('/platform/login/',HTTP_HOST=HOST)
    assert central.status_code==200 and b'branding/seer-logo.png' in central.content
    private=client.get('/platform/workspaces/annam/manage/login/',HTTP_HOST=HOST,follow=True)
    assert private.status_code==200 and private.resolver_match.view_name=='portal:login'


def test_local_management_deep_link_returns_to_that_host_after_login(client,owner):
    response=client.get('/manage/orders/?status=preparing',HTTP_HOST=HOST)
    login_url=urlsplit(response['Location'])
    assert login_url.path=='/manage/login/'
    target=parse_qs(login_url.query)['next'][0]
    assert target=='/manage/orders/?status=preparing'
    response=client.post('/manage/login/',credentials(next=target),HTTP_HOST=HOST)
    assert response['Location']==target
    assert client.get(target,HTTP_HOST=HOST).status_code==200


def test_private_workspace_deep_links_still_use_the_platform_login(client,owner):
    target='/platform/workspaces/annam/manage/orders/?status=preparing'
    response=client.get(target,HTTP_HOST=HOST)
    assert urlsplit(response['Location']).path=='/platform/login/'
    response=client.post('/platform/login/',credentials(next=target),HTTP_HOST=HOST)
    assert response['Location']==target


def test_kitchen_login_refuses_another_kitchens_owner(client,owner):
    response=client.post('/manage/login/',credentials(),HTTP_HOST=OTHER)
    assert response.status_code==200 and response.context['form'].non_field_errors()
    assert '_auth_user_id' not in client.session
    assert b'can\xe2\x80\x99t manage this store' in response.content
    assert client.get('/manage/',HTTP_HOST=OTHER).status_code==302


def test_local_logout_returns_to_local_login_and_workspace_logout_returns_to_seer(signed_in,owner):
    response=signed_in.post('/manage/logout/',HTTP_HOST=HOST)
    assert response['Location']=='/manage/login/'
    assert '_auth_user_id' not in signed_in.session
    signed_in.force_login(owner)
    response=signed_in.post('/platform/workspaces/annam/manage/logout/',HTTP_HOST=HOST)
    assert response['Location']=='/platform/login/'
    assert '_auth_user_id' not in signed_in.session


def test_no_membership_and_inactive_accounts_do_not_gain_kitchen_access(client,kitchens):
    user=get_user_model().objects.create_user('no-kitchen',password='test-only-account-password')
    response=client.post('/platform/login/',{'username':user.username,'password':'test-only-account-password'},HTTP_HOST=HOST)
    assert response['Location']=='/platform/'
    assert b'No kitchen access yet' in client.get('/platform/',HTTP_HOST=HOST).content
    assert client.get('/platform/workspaces/annam/manage/',HTTP_HOST=HOST).status_code==404
    client.logout();user.is_active=False;user.save(update_fields=['is_active'])
    response=client.post('/platform/login/',{'username':user.username,'password':'test-only-account-password'},HTTP_HOST=HOST)
    assert response.status_code==200 and response.context['form'].errors
    assert '_auth_user_id' not in client.session


def test_billing_still_has_its_own_login_on_public_and_workspace_routes(client,owner,kitchens):
    for root in ('/billing/','/platform/workspaces/annam/billing/'):
        browser=Client()
        response=browser.get(root,HTTP_HOST=HOST)
        assert response.status_code==302 and urlsplit(response['Location']).path==root+'login/'
        page=browser.get(response['Location'],HTTP_HOST=HOST)
        assert page.status_code==200 and page.resolver_match.view_name=='billing:login'
        target=parse_qs(urlsplit(response['Location']).query)['next'][0]
        response=browser.post(root+'login/',credentials(next=target),HTTP_HOST=HOST)
        assert response.status_code==302 and response['Location']==root
        assert browser.get(root,HTTP_HOST=HOST).status_code==200
        response=browser.post(root+'logout/',HTTP_HOST=HOST)
        assert response['Location']==root+'login/'
        assert browser.get(response['Location'],HTTP_HOST=HOST).status_code==200


def test_shared_login_keeps_csrf_protection(owner,kitchens):
    strict=Client(enforce_csrf_checks=True)
    assert strict.post('/platform/login/',credentials(),HTTP_HOST=HOST).status_code==403


@pytest.mark.parametrize('target',[
    'https://evil.example/','//evil.example/','http://[invalid',
    '/platform/admin/','/platform/workspaces/rival/manage/',
    '/billing/','/manage/login/','/manage/logout/',
    '/manage/../platform/admin/','/manage/%2e%2e/platform/admin/',
    '/manage/\\evil.example/',
])
def test_kitchen_login_never_redirects_outside_its_management_area(client,owner,target):
    response=client.post('/manage/login/',credentials(next=target),HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']=='/manage/'


def test_platform_superuser_can_use_local_login_but_stays_in_that_kitchen(client,operator,kitchens):
    response=client.post('/manage/login/',{'username':operator.username,'password':'Only-for-tests-928!'},HTTP_HOST=HOST)
    assert response.status_code==302 and response['Location']=='/manage/'
    assert client.get('/manage/',HTTP_HOST=HOST).wsgi_request.tenant.pk==kitchens[0].pk


def test_multi_kitchen_account_using_local_login_does_not_get_a_picker(client,owner,kitchens):
    with tenant_context(kitchens[1]):TenantUser.objects.create(user=owner,role='manager')
    response=client.post('/manage/login/',credentials(),HTTP_HOST=OTHER)
    assert response['Location']=='/manage/'
    assert client.get('/manage/',HTTP_HOST=OTHER).wsgi_request.tenant.pk==kitchens[1].pk


def test_local_kitchen_login_remains_csrf_protected_and_not_cached(owner,kitchens):
    strict=Client(enforce_csrf_checks=True)
    assert strict.post('/manage/login/',credentials(),HTTP_HOST=HOST).status_code==403
    page=strict.get('/manage/login/',HTTP_HOST=HOST)
    assert 'no-store' in page['Cache-Control']
