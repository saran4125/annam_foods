from datetime import timedelta
from unittest.mock import Mock, patch
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, override_settings
from django.utils import timezone
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST, OTHER
from apps.tenancy.context import tenant_context
from apps.tenancy.models import CustomDomain, TenantDomain, TenantUser, PlatformAuditEvent
from apps.platform_portal import domain_services as services, domain_network as network


@pytest.fixture
def claim(owner, kitchens):
    return services.add_domain(actor=owner, tenant=kitchens[0], hostname='www.customer-kitchen.com')


@pytest.fixture
def dns_ok(claim, settings):
    settings.DOMAIN_CNAME_TARGET = 'platform-host.onrender.com'
    def records(hostname, kind):
        if kind == 'TXT':
            return [claim.verification_token]
        if kind == 'CNAME':
            return ['platform-host.onrender.com']
        return ['8.8.8.8'] if kind == 'A' else []
    with patch.object(network, 'dns_records', side_effect=records) as lookup:
        yield lookup


def connect(owner, kitchens, claim, settings):
    settings.DOMAIN_CONNECTIONS_ENABLED = True
    settings.DOMAIN_HOSTING_PROVIDER = 'manual'
    with patch.object(network, 'check_https'):
        return services.connect_domain(actor=owner, tenant=kitchens[0], pk=claim.pk)


def test_domain_settings_are_private_and_only_owners_can_change_domains(client, signed_in, owner, kitchens):
    path = '/platform/workspaces/annam/domains/'
    assert Client().get(path, HTTP_HOST=HOST).status_code == 302
    assert signed_in.get(path, HTTP_HOST=HOST).status_code == 200
    assert signed_in.get('/platform/workspaces/rival/domains/', HTTP_HOST=HOST).status_code == 404
    with tenant_context(kitchens[0]):
        TenantUser.objects.filter(user=owner).update(role='staff')
    assert signed_in.get(path, HTTP_HOST=HOST).status_code == 403
    assert signed_in.post(path, {'action':'add','hostname':'shop.staff-example.com'}, HTTP_HOST=HOST).status_code == 403


def test_adding_domain_shows_records_without_changing_live_mapping(signed_in, kitchens):
    response = signed_in.post('/platform/workspaces/annam/domains/', {'action':'add','hostname':' WWW.CUSTOMER-KITCHEN.COM. '}, HTTP_HOST=HOST)
    assert response.status_code == 302
    with tenant_context(kitchens[0]):
        domain = CustomDomain.objects.get()
        assert domain.hostname == 'www.customer-kitchen.com'
        assert domain.txt_name == '_seerkitchen.www.customer-kitchen.com'
        assert PlatformAuditEvent.objects.filter(action='domain_added').exists()
    assert not TenantDomain.objects.filter(hostname=domain.hostname).exists()
    page = signed_in.get(response['Location'], HTTP_HOST=HOST)
    assert b'Prepare now. Connect at launch.' in page.content
    assert domain.verification_token.encode() in page.content
    assert signed_in.get('/', HTTP_HOST=domain.hostname).status_code == 404


@pytest.mark.parametrize('hostname', ['https://customer.com/path','customer.com:443','*.customer.com','127.0.0.1','[::1]','localhost','x.local','x.internal','x.onrender.com','bad..com','-bad.com','evil.com/path','user@customer.com','admin.localhost'])
def test_invalid_or_platform_domains_cannot_be_claimed(hostname):
    with pytest.raises(ValidationError):
        services.normalize_hostname(hostname)


def test_duplicate_pending_or_live_domain_cannot_be_assigned_to_another_kitchen(claim, kitchens, owner):
    with pytest.raises(ValidationError):
        services.add_domain(actor=owner, tenant=kitchens[0], hostname=claim.hostname)
    admin = get_user_model().objects.create_superuser('domain-admin','admin@example.com','test-password')
    with pytest.raises(ValidationError):
        services.add_domain(actor=admin, tenant=kitchens[1], hostname=claim.hostname)
    with pytest.raises(ValidationError):
        services.add_domain(actor=owner, tenant=kitchens[0], hostname=OTHER)


def test_a_dns_pointer_without_ownership_proof_never_creates_a_route(owner, kitchens, claim, dns_ok):
    dns_ok.side_effect = lambda *args: []
    result = services.check_domain(actor=owner, tenant=kitchens[0], pk=claim.pk)
    assert result.status == 'ownership_pending' and result.ownership_verified_at is None
    assert not TenantDomain.objects.filter(hostname=claim.hostname).exists()


def test_prepare_mode_verifies_dns_but_never_registers_hosting_or_connects(owner, kitchens, claim, dns_ok, settings):
    settings.DOMAIN_CONNECTIONS_ENABLED = False
    with patch.object(network,'register_render') as register, patch.object(network,'check_https') as https:
        result = services.connect_domain(actor=owner, tenant=kitchens[0], pk=claim.pk)
    assert result.ownership_verified_at and result.dns_verified_at
    assert not result.connection_requested_at and not result.mapping_id
    register.assert_not_called(); https.assert_not_called()
    assert not TenantDomain.objects.filter(hostname=claim.hostname).exists()


def test_failed_destination_or_resolver_is_reported_without_connecting(owner, kitchens, claim, dns_ok):
    with patch.object(network,'check_destination',side_effect=network.DomainCheckError('DNS not ready')):
        result = services.check_domain(actor=owner, tenant=kitchens[0], pk=claim.pk)
    assert result.status == 'dns_pending' and result.detail == 'DNS not ready'
    assert result.ownership_verified_at and not result.dns_verified_at


def test_public_destination_check_rejects_private_and_mixed_addresses():
    for answers in (['127.0.0.1'], ['169.254.169.254'], ['8.8.8.8','10.0.0.1'], ['::1'], ['garbage']):
        with patch.object(network,'dns_records',side_effect=[answers, []]):
            with pytest.raises(network.DomainCheckError): network.public_addresses('customer-kitchen.com')


def test_https_failure_keeps_domain_unrouted_and_primary_unchanged(owner, kitchens, claim, dns_ok, settings):
    settings.DOMAIN_CONNECTIONS_ENABLED = True;settings.DOMAIN_HOSTING_PROVIDER = 'manual'
    with patch.object(network,'check_https',side_effect=network.DomainCheckError('Certificate pending')):
        result = services.connect_domain(actor=owner, tenant=kitchens[0], pk=claim.pk)
    assert result.status == 'hosting_pending' and not result.mapping_id
    assert result.connection_requested_at and not result.tls_verified_at
    assert not TenantDomain.objects.filter(hostname=claim.hostname).exists()
    assert TenantDomain.objects.get(hostname=HOST).is_primary


def test_https_activation_and_explicit_primary_change_preserve_tools_and_post_routes(owner, kitchens, claim, dns_ok, settings, signed_in):
    result = connect(owner, kitchens, claim, settings)
    assert result.status == 'active' and result.mapping.tenant_id == kitchens[0].pk and result.tls_verified_at
    assert not result.mapping.is_primary
    assert signed_in.get('/', HTTP_HOST=claim.hostname).status_code == 200
    services.make_primary(actor=owner, tenant=kitchens[0], pk=claim.pk)
    page = signed_in.get('/menu/?date=2026-10-21', HTTP_HOST=HOST)
    assert page.status_code == 301 and page['Location'] == 'https://'+claim.hostname+'/menu/?date=2026-10-21'
    assert signed_in.get('/manage/', HTTP_HOST=HOST).status_code == 200
    assert signed_in.get('/billing/', HTTP_HOST=HOST).status_code == 200
    assert signed_in.get('/platform/', HTTP_HOST=HOST).status_code == 200
    assert signed_in.post('/menu/', HTTP_HOST=HOST).status_code != 301
    assert signed_in.get('/', HTTP_HOST=claim.hostname).status_code == 200
    assert signed_in.get('/', HTTP_HOST=OTHER).status_code == 200
    with pytest.raises(ValidationError): services.remove_domain(actor=owner, tenant=kitchens[0], pk=claim.pk)


def test_only_active_recent_https_domain_can_be_primary(owner, kitchens, claim, dns_ok, settings):
    with pytest.raises(ValidationError): services.make_primary(actor=owner, tenant=kitchens[0], pk=claim.pk)
    connect(owner, kitchens, claim, settings)
    with tenant_context(kitchens[0]): CustomDomain.objects.filter(pk=claim.pk).update(tls_verified_at=timezone.now()-timedelta(days=2))
    with pytest.raises(ValidationError): services.make_primary(actor=owner, tenant=kitchens[0], pk=claim.pk)


def test_owner_cannot_check_or_remove_other_kitchens_claim(signed_in, owner, kitchens, claim):
    other = get_user_model().objects.create_user('other-owner')
    with tenant_context(kitchens[1]): TenantUser.objects.create(user=other,role='owner')
    other_domain = services.add_domain(actor=other, tenant=kitchens[1], hostname='shop.other-kitchen.com')
    for action in ('verify','connect','primary','remove'):
        page=signed_in.post('/platform/workspaces/annam/domains/', {'action':action,'domain_id':other_domain.pk},HTTP_HOST=HOST)
        assert page.status_code == 404


def test_domain_forms_keep_csrf_protection(owner, kitchens):
    strict=Client(enforce_csrf_checks=True);strict.force_login(owner)
    assert strict.post('/platform/workspaces/annam/domains/', {'action':'add','hostname':'customer.com'},HTTP_HOST=HOST).status_code == 403


def test_pending_domain_serves_only_nonce_proof_and_is_admitted_without_global_wildcard(owner, kitchens, claim, dns_ok, settings, client):
    settings.DOMAIN_CONNECTIONS_ENABLED=True;settings.DOMAIN_HOSTING_PROVIDER='manual'
    with patch.object(network,'check_https',side_effect=network.DomainCheckError('pending')):
        services.connect_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    settings.ALLOWED_HOSTS = [HOST]
    nonce='a'*32
    response=client.get('/.well-known/seerkitchen-domain',{'nonce':nonce},HTTP_HOST=claim.hostname)
    assert response.status_code == 200
    assert response.json()['proof']==network.domain_proof(claim.hostname,claim.verification_token,nonce)
    assert client.get('/',HTTP_HOST=claim.hostname).status_code==404
    assert client.get('/.well-known/seerkitchen-domain',{'nonce':nonce},HTTP_HOST='unapproved-customer.com').status_code==400
    assert settings.ALLOWED_HOSTS == [HOST]
    assert client.get('/.well-known/seerkitchen-domain',{'nonce':'invalid'},HTTP_HOST=claim.hostname).status_code==404


def test_caddy_certificate_requests_require_explicit_verified_connection(owner, kitchens, claim, dns_ok, settings, client):
    settings.DOMAIN_CONNECTIONS_ENABLED=True;settings.DOMAIN_HOSTING_PROVIDER='caddy'
    url='/platform/domains/allow-certificate/'
    assert client.get(url,{'domain':claim.hostname},HTTP_HOST=HOST).status_code==403
    with patch.object(network,'check_https',side_effect=network.DomainCheckError('pending')):
        services.connect_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    assert client.get(url,{'domain':claim.hostname},HTTP_HOST=HOST).status_code==200
    assert client.get(url,{'domain':'unapproved.com'},HTTP_HOST=HOST).status_code==403


def test_removing_non_primary_domain_removes_route_and_records_audit(owner, kitchens, claim, dns_ok, settings):
    result=connect(owner,kitchens,claim,settings)
    services.remove_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    assert not TenantDomain.objects.filter(pk=result.mapping_id).exists()
    assert not CustomDomain.all_tenants.filter(pk=claim.pk).exists()
    assert TenantDomain.objects.get(hostname=HOST).is_primary
    assert PlatformAuditEvent.all_tenants.filter(tenant=kitchens[0],action='domain_removed').exists()


def test_render_registration_is_reconciled_and_not_duplicated_after_retry(settings):
    settings.RENDER_API_KEY='test-provider-key';settings.RENDER_SERVICE_ID='srv-test'
    with patch.object(network,'_render',side_effect=[[{'customDomain':{'name':'www.customer.com','id':'cd-existing'}}]]) as api:
        assert network.register_render('www.customer.com')=='cd-existing'
        assert api.call_count == 1
    with patch.object(network,'_render',side_effect=[[], {'id':'cd-new'}]) as api:
        assert network.register_render('www.customer.com')=='cd-new'
        assert api.call_args.args[0]=='POST'


def test_render_registration_is_only_attempted_after_verified_dns(owner,kitchens,claim,dns_ok,settings):
    settings.DOMAIN_CONNECTIONS_ENABLED=True;settings.DOMAIN_HOSTING_PROVIDER='render'
    with patch.object(network,'register_render',return_value='cd-new') as register,patch.object(network,'verify_render') as verify,patch.object(network,'check_https'):
        result=services.connect_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    register.assert_called_once_with(claim.hostname,'');verify.assert_called_once_with('cd-new')
    assert result.provider_id=='cd-new' and result.status=='active'
    with patch.object(network,'remove_render') as remove:
        services.remove_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    remove.assert_called_once_with('cd-new')


def test_disabling_production_connections_blocks_primary_changes_too(owner,kitchens,claim,dns_ok,settings):
    connect(owner,kitchens,claim,settings)
    settings.DOMAIN_CONNECTIONS_ENABLED=False
    with pytest.raises(ValidationError):services.make_primary(actor=owner,tenant=kitchens[0],pk=claim.pk)
    assert TenantDomain.objects.get(hostname=HOST).is_primary


def test_https_probe_rejects_redirects_wrong_application_and_private_addresses(settings):
    settings.SECRET_KEY='test-server-proof-key'
    response=Mock()
    response.status=301;response.read.return_value=b'{}'
    with patch.object(network,'PinnedHTTPSConnection') as connection:
        connection.return_value.getresponse.return_value=response
        with pytest.raises(network.DomainCheckError):network.check_https('www.customer.com','token',{'8.8.8.8'})
        connection.return_value.request.assert_called_once()
    response.status=200;response.read.return_value=b'{"proof":"wrong-application"}'
    with patch.object(network,'PinnedHTTPSConnection') as connection:
        connection.return_value.getresponse.return_value=response
        with pytest.raises(network.DomainCheckError):network.check_https('www.customer.com','token',{'8.8.8.8'})
    with patch.object(network,'PinnedHTTPSConnection') as connection:
        with pytest.raises(network.DomainCheckError):network.check_https('www.customer.com','token',{'127.0.0.1','8.8.8.8'})
        connection.assert_not_called()


def test_https_probe_accepts_only_fresh_signed_proof_from_correct_hostname(settings):
    import json
    from unittest.mock import Mock
    settings.SECRET_KEY='test-server-proof-key';nonce='a'*32
    response=Mock(status=200);response.read.return_value=json.dumps({'proof':network.domain_proof('www.customer.com','token',nonce)}).encode()
    with patch.object(network.secrets,'token_hex',return_value=nonce),patch.object(network,'PinnedHTTPSConnection') as connection:
        connection.return_value.getresponse.return_value=response
        network.check_https('www.customer.com','token',{'8.8.8.8'})
        connection.assert_called_once_with('www.customer.com','8.8.8.8')
        connection.return_value.close.assert_called_once()


def test_rechecking_connected_domain_preserves_its_route_during_dns_trouble(owner,kitchens,claim,dns_ok,settings):
    connected=connect(owner,kitchens,claim,settings)
    with tenant_context(kitchens[0]):CustomDomain.objects.filter(pk=claim.pk).update(checked_at=timezone.now()-timedelta(minutes=1))
    with patch.object(network,'dns_records',side_effect=network.DomainCheckError('Temporary resolver issue')):
        result=services.check_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    assert result.status=='attention' and result.mapping_id==connected.mapping_id
    assert TenantDomain.objects.filter(hostname=claim.hostname,tenant=kitchens[0]).exists()


def test_render_failure_keeps_credentials_private_and_domain_unrouted(owner,kitchens,claim,dns_ok,settings):
    settings.DOMAIN_CONNECTIONS_ENABLED=True;settings.DOMAIN_HOSTING_PROVIDER='render';settings.RENDER_API_KEY='do-not-display-this-key';settings.RENDER_SERVICE_ID='srv-test'
    from urllib.error import HTTPError
    with patch.object(network,'_json_request',side_effect=HTTPError('https://api.render.com',401,'unauthorized',{},None)):
        result=services.connect_domain(actor=owner,tenant=kitchens[0],pk=claim.pk)
    assert settings.RENDER_API_KEY not in result.detail
    assert not result.mapping_id and result.status=='hosting_pending'


def test_dns_txt_split_records_and_trailing_cname_dots_are_normalized():
    with patch.object(network,'_json_request',return_value={'Status':0,'Answer':[{'type':16,'data':'"seerkitchen=" "abc"'}]}):
        assert network.dns_records('_seerkitchen.customer.com','TXT')==['seerkitchen=abc']
    with patch.object(network,'_json_request',return_value={'Status':0,'Answer':[{'type':5,'data':'HOST.ONRENDER.COM.'}]}):
        assert network.dns_records('www.customer.com','CNAME')==['host.onrender.com']


def test_bad_hosting_configuration_and_invalid_action_ids_do_not_break_settings(signed_in,settings):
    settings.DOMAIN_CNAME_TARGET='https://invalid.example.com/path'
    path='/platform/workspaces/annam/domains/'
    page=signed_in.get(path,HTTP_HOST=HOST)
    assert page.status_code==200 and b'hosting destination configuration' in page.content
    for identifier in ('not-an-id','²','9'*100):
        assert signed_in.post(path,{'action':'remove','domain_id':identifier},HTTP_HOST=HOST).status_code==400
