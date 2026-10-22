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


def test_local_management_deep_link_returns_to_that_host_after_login(client,owner):
    response=client.get('/manage/orders/?status=preparing',HTTP_HOST=HOST)
    login_url=urlsplit(response['Location'])
    assert login_url.path=='/manage/login/'
    target=parse_qs(login_url.query)['next'][0]
    assert target=='/manage/orders/?status=preparing'
    response=client.post('/manage/login/',credentials(next=target),HTTP_HOST=HOST)
    assert response['Location']==target
    assert client.get(target,HTTP_HOST=HOST).status_code==200


def test_kitchen_login_refuses_another_kitchens_owner(client,owner):
    response=client.post('/manage/login/',credentials(),HTTP_HOST=OTHER)
    assert response.status_code==200 and response.context['form'].non_field_errors()
    assert '_auth_user_id' not in client.session
    assert b'can\xe2\x80\x99t manage this store' in response.content
    assert client.get('/manage/',HTTP_HOST=OTHER).status_code==302


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
