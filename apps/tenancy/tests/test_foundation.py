"""Phase A contracts: configuration is data and cross-kitchen work stays scoped."""
from datetime import datetime, date, time
from decimal import Decimal
from pathlib import Path
import re
from threading import Event, Thread
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.utils import timezone

from apps.catalog.models import MenuItem, Slot
from apps.jobs.models import DailyKitchenRun
from apps.jobs.services import run_daily_handoff
from apps.tenancy.context import tenant_context
from apps.tenancy.features import FEATURES
from apps.tenancy.models import BillingProfile, Tenant, TenantConfig
from apps.tenancy.presets import preset_names


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(FEATURES))
def test_each_flag_has_a_registry_default_and_both_explicit_states(name):
    tenant = Tenant.objects.create(slug="flag-example-" + name.replace("_", "-"), name="Flag kitchen")
    config = tenant.config
    assert tenant.feature(name) is FEATURES[name].default
    for state in (True, False):
        config.features = {name: state}
        config.save()
        assert tenant.feature(name) is state


@pytest.mark.django_db
def test_unknown_or_non_boolean_flag_fails_closed():
    tenant = Tenant.objects.create(slug="flags", name="Flags")
    config = tenant.config
    with pytest.raises(KeyError):
        tenant.feature("made_up_feature")
    config.features = {"cod": "yes"}
    with pytest.raises(ValueError):
        tenant.feature("cod")
    with pytest.raises(ValidationError):
        config.full_clean()


@pytest.mark.django_db
def test_a_feature_lookup_repairs_a_missing_tenant_config():
    tenant = Tenant.objects.create(slug="without-config", name="Without Config")
    tenant.config.delete()
    assert tenant.feature("cod") is FEATURES["cod"].default
    assert TenantConfig.objects.filter(tenant=tenant).exists()


@pytest.mark.django_db
def test_unknown_registry_flag_is_reported_as_a_form_validation_error():
    tenant = Tenant.objects.create(slug="invalid-flags", name="Invalid Flags")
    config = tenant.config
    config.features = {"not_registered": True}
    config.save()
    with pytest.raises(ValidationError) as exc:
        config.full_clean()
    assert "features" in exc.value.message_dict


@pytest.mark.django_db
def test_billing_profile_defaults_and_number_format_validation():
    tenant = Tenant.objects.create(slug="billing-defaults", name="Billing Defaults")
    profile = BillingProfile(tenant=tenant)
    assert profile.tax_rate == Decimal("5")
    assert profile.sac == "996331"
    assert profile.round_total and profile.delivery_fee_taxable
    assert profile.number_format.format(prefix=profile.invoice_prefix, fy="26-27", seq=12) == "AF/26-27/00012"
    profile.number_format = "TOO-LONG-PREFIX/{fy}/{seq:05d}"
    with pytest.raises(ValidationError, match="at most 16 characters"):
        profile.full_clean()
    profile.number_format = "{prefix}/{fy}/₹{seq:05d}"
    with pytest.raises(ValidationError, match="only letters"):
        profile.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("preset", preset_names())
def test_every_preset_provisions_a_clean_kitchen_with_draft_pages(preset):
    from apps.content.models import Page
    from django.test import Client
    slug = "fixture-" + preset
    call_command("provision_tenant", slug=slug, name="Fixture kitchen", domain=slug + ".localhost",
                 owner_email=slug + "@example.test", preset=preset, stdout=open("/dev/null", "w"))
    tenant = Tenant.objects.get(slug=slug)
    with tenant_context(tenant):
        assert tenant.config.preset_name == preset
        assert tenant.config.preset_data["template_pack"]
        assert Page.objects.exists()
        assert not Page.objects.filter(published=True).exists()
        if preset == "daily-meals":
            assert Slot.objects.count() == 3
        else:
            assert not Slot.objects.exists()
        assert Client().get("/", HTTP_HOST=slug + ".localhost").status_code == 200
        BillingProfile.objects.get(tenant=tenant)


@pytest.mark.django_db
def test_retailer_identifiers_are_unique_within_a_kitchen_but_not_across_kitchens():
    from django.db import IntegrityError
    first = Tenant.objects.create(slug="first", name="First")
    second = Tenant.objects.create(slug="second", name="Second")
    with tenant_context(first):
        MenuItem.objects.create(name="One", price=Decimal("10"), retailer_id="SKU-1")
        with pytest.raises(IntegrityError), transaction.atomic():
            MenuItem.objects.create(name="Two", price=Decimal("20"), retailer_id="SKU-1")
    with tenant_context(second):
        MenuItem.objects.create(name="Three", price=Decimal("30"), retailer_id="SKU-1")
        assert list(MenuItem.objects.values_list("name", flat=True)) == ["Three"]


@pytest.mark.django_db
def test_daily_scheduler_uses_each_local_date_once_at_noon_and_2330():
    a = Tenant.objects.create(slug="east", name="East")
    b = Tenant.objects.create(slug="west", name="West")
    TenantConfig.objects.filter(tenant=a).update(timezone="Asia/Kolkata")
    TenantConfig.objects.filter(tenant=b).update(timezone="America/Los_Angeles")
    for hour, minute in ((12, 0), (23, 30)):
        instant = datetime(2026, 9, 28, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata"))
        first = run_daily_handoff(instant)
        assert all(day == instant.astimezone(ZoneInfo(TenantConfig.objects.get(tenant_id=tid).timezone)).date().isoformat() for tid, day in first)
        assert run_daily_handoff(instant) == []
    with tenant_context(a):
        assert DailyKitchenRun.objects.count() == 1
    with tenant_context(b):
        assert DailyKitchenRun.objects.count() == 2  # two local dates across the IST test times


@pytest.mark.django_db
def test_application_code_never_branches_on_a_customer_slug():
    root = Path(__file__).resolve().parents[2]
    offenders = []
    source_files = (p for p in root.rglob("*") if p.is_file() and (
        p.suffix == ".py" or "templates" in p.parts or "static" in p.parts
    ))
    for path in source_files:
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        if re.search(r"\b(?:tenant|kitchen)\.slug\s*(?:==|!=|in\s+)\s*['\"][A-Za-z0-9_-]+['\"]", text):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def test_money_display_preserves_paise_instead_of_rounding():
    from apps.storefront.templatetags.storefront_extras import money
    assert money(Decimal("120.50")) == "120.50"
    assert money(Decimal("120.99")) == "120.99"


@pytest.mark.django_db(transaction=True)
def test_postgres_row_lock_blocks_a_second_writer_until_commit():
    assert connections["default"].vendor == "postgresql"
    tenant = Tenant.objects.create(slug="lock", name="Lock")
    config = tenant.config
    holding = Event()
    release = Event()
    second_waiting = Event()
    second_acquired = Event()
    errors = []

    def first_writer():
        try:
            with transaction.atomic():
                TenantConfig.objects.select_for_update().get(tenant=tenant)
                holding.set()
                assert release.wait(10)
        except Exception as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    def second_writer():
        try:
            assert holding.wait(10)
            with transaction.atomic():
                second_waiting.set()
                TenantConfig.objects.select_for_update().get(tenant=tenant)
                second_acquired.set()
        except Exception as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    left = Thread(target=first_writer)
    right = Thread(target=second_writer)
    left.start(); right.start()
    try:
        assert holding.wait(10)
        assert second_waiting.wait(10)
        assert not second_acquired.wait(0.2)
    finally:
        release.set()
        left.join(10); right.join(10)
    assert not errors
    assert second_acquired.is_set()
