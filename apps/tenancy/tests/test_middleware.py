import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from apps.tenancy.middleware import TenantMiddleware
from apps.tenancy.models import Tenant, TenantConfig, TenantDomain


@pytest.fixture
def annam(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    TenantDomain.objects.create(tenant=t, hostname="annam.localhost", is_primary=True)
    return t


def test_known_host_resolves_a_tenant(client, annam):
    response = client.get("/admin/login/", HTTP_HOST="annam.localhost")
    assert response.wsgi_request.tenant == annam


def test_unknown_host_is_not_served(client, db):
    response = client.get("/", HTTP_HOST="nobody.example.com")
    assert response.status_code == 404


def test_health_check_does_not_require_a_registered_tenant_host(client, db):
    response = client.get("/healthz", HTTP_HOST="health.example.test")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_platform_host_carries_no_tenant(client, annam, settings):
    settings.PLATFORM_HOST = "admin.localhost"
    response = client.get("/admin/login/", HTTP_HOST="admin.localhost")
    assert response.wsgi_request.tenant is None


def test_hostname_matching_ignores_case_and_port(client, annam):
    response = client.get("/admin/login/", HTTP_HOST="ANNAM.localhost:8000")
    assert response.wsgi_request.tenant == annam


def test_django_admin_is_blocked_on_tenant_hosts(client, annam):
    """(FIX-11) Vendor admin is a platform surface, not a kitchen one."""
    response = client.get("/admin/login/", HTTP_HOST="annam.localhost")
    assert response.status_code == 404


def test_retired_django_admin_is_not_available_on_the_old_platform_host(client, annam, settings):
    settings.PLATFORM_HOST = "admin.localhost"
    response = client.get("/admin/login/", HTTP_HOST="admin.localhost")
    assert response.status_code == 404


def test_a_kitchens_clock_is_its_own_while_serving(client, annam):
    """(FIX-10) The middleware operates in the tenant's timezone, so cutoffs
    and menus are read at local midnight, not the server's."""
    TenantConfig.objects.filter(tenant=annam).update(brand_name="Annam", timezone="America/Sao_Paulo")
    captured = {}

    def get_response(request):
        captured["zone"] = str(timezone.get_current_timezone())
        return HttpResponse("ok")

    request = RequestFactory().get("/", HTTP_HOST="annam.localhost")
    response = TenantMiddleware(get_response)(request)
    assert response.status_code == 200
    assert captured["zone"] == "America/Sao_Paulo"
    # Outside the request the default clock is back; an early-returning
    # middleware must not leak its timezone into the whole process.
    assert str(timezone.get_current_timezone()) != "America/Sao_Paulo"


def test_a_kitchens_request_restores_the_prior_active_timezone(annam):
    TenantConfig.objects.filter(tenant=annam).update(timezone="America/Sao_Paulo")
    timezone.activate("Europe/London")
    try:
        request = RequestFactory().get("/", HTTP_HOST="annam.localhost")
        TenantMiddleware(lambda request: HttpResponse("ok"))(request)
        assert str(timezone.get_current_timezone()) == "Europe/London"
    finally:
        timezone.deactivate()
