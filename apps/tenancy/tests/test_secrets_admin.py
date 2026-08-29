"""The portal must never hand a stored secret back to a browser."""
import pytest
from django.contrib.auth.models import User

from apps.tenancy.forms import TenantSecretsForm
from apps.tenancy.models import Tenant, TenantSecrets


@pytest.fixture
def secrets(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    s = TenantSecrets.objects.create(tenant=t)
    s.wa_token = "EAFZBpLx8ZChvQ-very-secret"
    s.save()
    return s


def test_the_form_shows_a_mask_never_the_secret(secrets):
    form = TenantSecretsForm(instance=secrets)
    rendered = form.as_p()
    assert "EAFZBpLx8ZChvQ-very-secret" not in rendered
    assert "••••••••" in form.fields["new_wa_token"].help_text


def test_a_blank_input_keeps_the_existing_secret(secrets):
    form = TenantSecretsForm(
        instance=secrets,
        data={"wa_provider": secrets.wa_provider, "new_wa_token": ""},
    )
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.wa_token == "EAFZBpLx8ZChvQ-very-secret"


def test_a_filled_input_replaces_it(secrets):
    form = TenantSecretsForm(
        instance=secrets,
        data={"wa_provider": secrets.wa_provider, "new_wa_token": "rotated-token"},
    )
    assert form.is_valid(), form.errors
    assert form.save().wa_token == "rotated-token"


def test_the_admin_change_page_never_renders_a_secret(client, secrets, db):
    admin_user = User.objects.create_superuser("root", "root@example.com", "pw")
    client.force_login(admin_user)
    r = client.get(
        f"/admin/tenancy/tenantsecrets/{secrets.pk}/change/",
        HTTP_HOST="admin.localhost",
    )
    assert r.status_code == 200
    assert b"EAFZBpLx8ZChvQ-very-secret" not in r.content
