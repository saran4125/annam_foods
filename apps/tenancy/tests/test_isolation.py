"""The tests that stop one kitchen seeing another kitchen's data.

If any of these fail, do not ship. A cross-tenant leak is the single worst bug
this product can have.
"""
import pytest
from django.apps import apps
from django.contrib.auth.models import User

from apps.tenancy.context import (
    TenantContextMissing,
    all_tenants,
    get_current_tenant,
    tenant_context,
)
from apps.tenancy.managers import TenantOwnedModel, TenantScopedManager
from apps.tenancy.models import Tenant, TenantDomain, TenantUser


@pytest.fixture
def annam(db):
    t = Tenant.objects.create(slug="annam", name="Annam Foods", status="active")
    TenantDomain.objects.create(tenant=t, hostname="annam.localhost", is_primary=True)
    return t


@pytest.fixture
def other(db):
    t = Tenant.objects.create(slug="rival", name="Rival Kitchen", status="active")
    TenantDomain.objects.create(tenant=t, hostname="rival.localhost", is_primary=True)
    return t


# --- the tripwire -----------------------------------------------------------

def test_every_tenant_owned_model_uses_the_scoped_manager():
    """Registering a model with a `tenant` FK but no scoped manager is exactly
    how a leak gets shipped. Fail the build instead of trusting memory."""
    offenders = []
    for model in apps.get_models():
        field_names = {f.name for f in model._meta.get_fields()}
        if "tenant" not in field_names:
            continue
        if model is Tenant:
            continue
        # A model may opt out, but only by saying so on the model itself with
        # a reason -- never by being quietly added to a list in this test.
        if getattr(model, "tenant_scoping_exempt", None):
            continue
        if not issubclass(model, TenantOwnedModel):
            offenders.append(f"{model._meta.label}: does not subclass TenantOwnedModel")
            continue
        if not isinstance(model._default_manager, TenantScopedManager):
            offenders.append(
                f"{model._meta.label}: default manager is "
                f"{type(model._default_manager).__name__}, not TenantScopedManager"
            )
    assert not offenders, "Tenant-owned models without scoping:\n" + "\n".join(offenders)


# --- fail closed ------------------------------------------------------------

def test_querying_without_a_tenant_raises(db):
    with pytest.raises(TenantContextMissing):
        list(TenantUser.objects.all())


def test_saving_without_a_tenant_raises(db):
    user = User.objects.create_user("nobody")
    with pytest.raises(TenantContextMissing):
        TenantUser(user=user, role="owner").save()


# --- scoping actually scopes ------------------------------------------------

def test_queries_only_see_the_current_tenant(annam, other):
    a_user = User.objects.create_user("annam-owner")
    b_user = User.objects.create_user("rival-owner")
    TenantUser.all_tenants.create(tenant=annam, user=a_user, role="owner")
    TenantUser.all_tenants.create(tenant=other, user=b_user, role="owner")

    with tenant_context(annam):
        rows = list(TenantUser.objects.all())
        assert len(rows) == 1
        assert rows[0].user == a_user

    with tenant_context(other):
        rows = list(TenantUser.objects.all())
        assert len(rows) == 1
        assert rows[0].user == b_user


def test_tenant_is_stamped_automatically_on_save(annam):
    user = User.objects.create_user("auto")
    with tenant_context(annam):
        membership = TenantUser(user=user, role="manager")
        membership.save()
    assert membership.tenant_id == annam.id


def test_all_tenants_is_the_only_way_across(annam, other):
    User.objects.create_user("a")
    User.objects.create_user("b")
    TenantUser.all_tenants.create(tenant=annam, user=User.objects.get(username="a"))
    TenantUser.all_tenants.create(tenant=other, user=User.objects.get(username="b"))

    with all_tenants():
        assert TenantUser.objects.count() == 2


def test_context_does_not_leak_out_of_the_block(annam):
    with tenant_context(annam):
        assert get_current_tenant() == annam
    assert get_current_tenant() is None
