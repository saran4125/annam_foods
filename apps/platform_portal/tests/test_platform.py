"""Preserved internal invitation/data services; browser provisioning is retired."""
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


def test_legacy_invitation_service_preserves_single_use_passwords(operator, kitchens):
    kitchen, invitation, token = provision_kitchen(actor=operator, **create_data())
    user, activated = accept_invitation(token=token, password='Strong-test-password-8x4!')
    assert activated and user.check_password('Strong-test-password-8x4!')
    assert invitation_for_token(token) is None
    with tenant_context(kitchen):
        assert TenantUser.objects.get(user=user).role == 'owner'


def test_existing_account_invitation_service_never_changes_password(operator, owner, kitchens):
    owner.email = 'known-owner@example.test'
    owner.save()
    invitation, token = invite_owner(actor=operator, tenant=kitchens[1], email=owner.email, role='manager')
    from django.core.exceptions import ValidationError
    with pytest.raises(ValidationError):
        accept_invitation(token=token, password='Do-not-change-this-password-82!')
    accept_invitation(token=token, signed_in_user=owner)
    owner.refresh_from_db()
    assert owner.check_password('pw-for-tests-only')
    with tenant_context(kitchens[1]):
        assert TenantUser.objects.get(user=owner).role == 'manager'


def test_reissuing_revokes_old_links_and_expired_invites_are_rejected(operator, kitchens):
    invitation, token=invite_owner(actor=operator,tenant=kitchens[0],email='invitee@example.test')
    second, token2=invite_owner(actor=operator,tenant=kitchens[0],email='invitee@example.test')
    assert invitation_for_token(token) is None
    assert invitation_for_token(token2).pk==second.pk
    OwnerInvitation.all_tenants.filter(pk=second.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
    with pytest.raises(Exception,match='expired'):
        accept_invitation(token=token2,password='Strong-test-password-8x4!')


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
