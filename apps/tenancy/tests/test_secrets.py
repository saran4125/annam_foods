"""Tenant credentials: encrypted at rest, never handed back to a browser."""
import pytest

from apps.tenancy.crypto import decrypt, encrypt, mask
from apps.tenancy.models import MessageProvider, Tenant, TenantSecrets


@pytest.fixture
def kitchen(db):
    return Tenant.objects.create(slug="annam", name="Annam Foods", status="active")


def test_a_secret_round_trips():
    assert decrypt(encrypt("hunter2")) == "hunter2"


def test_ciphertext_does_not_contain_the_plaintext():
    token = encrypt("EAFZBpLx8ZChvQBRFVz")
    assert "EAFZBpLx8ZChvQBRFVz" not in token


def test_stored_secrets_are_encrypted_in_the_column(kitchen):
    """Anyone reading the database directly must not find a usable token."""
    s = TenantSecrets.objects.create(tenant=kitchen)
    s.wa_token = "super-secret-token"
    s.save()
    s.refresh_from_db()
    assert s._wa_token != "super-secret-token"
    assert "super-secret-token" not in s._wa_token
    assert s.wa_token == "super-secret-token"


def test_an_empty_secret_stays_empty(kitchen):
    s = TenantSecrets.objects.create(tenant=kitchen)
    s.wa_token = ""
    s.save()
    assert s.wa_token == ""
    assert s._wa_token == ""


def test_mask_shows_only_the_last_four():
    assert mask("abcdefgh4f2a") == "••••••••4f2a"
    assert mask("") == ""


def test_a_wrong_key_raises_rather_than_looking_empty(kitchen, settings):
    """Silently returning '' would send unauthenticated requests to Meta."""
    s = TenantSecrets.objects.create(tenant=kitchen)
    s.wa_token = "real-token"
    s.save()
    settings.SECRETS_KEY = "ZBHHDJ3n5cJcOTBFqIxNiFN6BMRRDIsuDlWJ7cShAB0="
    s.refresh_from_db()
    with pytest.raises(RuntimeError, match="Wrong SECRETS_KEY"):
        _ = s.wa_token


def test_configuration_flags_reflect_what_is_actually_set(kitchen):
    s = TenantSecrets.objects.create(tenant=kitchen, wa_provider=MessageProvider.META_CLOUD)
    assert not s.whatsapp_is_configured
    s.wa_phone_number_id = "123"
    s.wa_token = "t"
    s.save()
    assert s.whatsapp_is_configured

    assert not s.razorpay_is_configured
    s.razorpay_key_id = "rzp_test_x"
    s.razorpay_secret = "shh"
    s.save()
    assert s.razorpay_is_configured


def test_n8n_provider_needs_a_url_not_a_meta_token(kitchen):
    s = TenantSecrets.objects.create(tenant=kitchen, wa_provider=MessageProvider.N8N)
    assert not s.whatsapp_is_configured
    s.n8n_send_url = "https://automation.seerbusiness.com/webhook/wa-send"
    s.save()
    assert s.whatsapp_is_configured


def test_secrets_are_exempt_from_scoping_with_a_stated_reason():
    assert TenantSecrets.tenant_scoping_exempt
