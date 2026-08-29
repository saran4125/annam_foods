import pytest

from apps.tenancy.models import Tenant, TenantDomain


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


def test_platform_host_carries_no_tenant(client, annam, settings):
    settings.PLATFORM_HOST = "admin.localhost"
    response = client.get("/admin/login/", HTTP_HOST="admin.localhost")
    assert response.wsgi_request.tenant is None


def test_hostname_matching_ignores_case_and_port(client, annam):
    response = client.get("/admin/login/", HTTP_HOST="ANNAM.localhost:8000")
    assert response.wsgi_request.tenant == annam
