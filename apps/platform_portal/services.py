"""Platform accounts, tenant routing, provisioning and invitations."""
import hashlib
import ipaddress
import re
import secrets
from urllib.parse import urlencode, urlsplit
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from apps.tenancy.context import tenant_context
from apps.tenancy.models import (Tenant, TenantConfig, TenantDomain, TenantStatus, TenantUser,
                                OwnerInvitation, PlatformAuditEvent)
from apps.tenancy.presets import apply_preset, preset_names

RESERVED = {"www", "app", "admin", "platform", "api", "mail", "support", "billing", "static", "media"}


def accessible_kitchens(user):
    if not user.is_authenticated or not user.is_active:
        return Tenant.objects.none()
    if user.is_superuser:
        return Tenant.objects.all()
    memberships = TenantUser.all_tenants.filter(user=user).values("tenant_id")
    return Tenant.objects.filter(pk__in=memberships)


def login_destination(user):
    if user.is_superuser:
        return reverse("portal:admin")
    kitchens = list(accessible_kitchens(user)[:2])
    if len(kitchens) == 1:
        return f"/platform/workspaces/{kitchens[0].slug}/manage/"
    return reverse("portal:home")


def management_login_url(request, target=""):
    """Old management bookmarks use the one shared sign-in, without credentials."""
    if target.startswith("/manage/") and getattr(request, "tenant", None):
        target = f"/platform/workspaces/{request.tenant.slug}" + target
    if not target.startswith("/platform/") or not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = ""
    return reverse("portal:login") + ("?" + urlencode({"next": target}) if target else "")


def authorized_login_target(request, user, target):
    """A saved destination never chooses an unauthorized kitchen or a login loop."""
    if not target.startswith("/platform/") or not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        return ""
    path = urlsplit(target).path
    if path in (reverse("portal:login"), reverse("portal:logout")):
        return ""
    if (path == "/platform/admin" or path.startswith("/platform/admin/")) and not user.is_superuser:
        return ""
    match = re.match(r"^/platform/workspaces/([^/]+)(?:/|$)", path)
    if match:
        if path.endswith(("/manage/login/", "/manage/logout/")) or not accessible_kitchens(user).filter(slug=match.group(1)).exists():
            return ""
    return target


def require_operator(user):
    if not user.is_authenticated or not user.is_active or not user.is_superuser:
        raise PermissionDenied("Platform administrator access is required.")


def normalized_slug(value):
    value = str(value).strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) or not 2 <= len(value) <= 60 or value in RESERVED:
        raise ValidationError("Use 2–60 lowercase letters/numbers with single hyphens; choose a non-reserved kitchen address.")
    return value


def base_domain():
    value = str(getattr(settings, "TENANT_BASE_DOMAIN", "") or "").strip().lower()
    if not value:
        return ""
    if value == "localhost":
        return value
    if len(value) > 190 or "." not in value or not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", value) or ".." in value:
        raise ValidationError("TENANT_BASE_DOMAIN must be a hostname without a scheme, path, port or wildcard.")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in value.split(".")):
        raise ValidationError("TENANT_BASE_DOMAIN contains an invalid hostname label.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValidationError("TENANT_BASE_DOMAIN must be a DNS hostname, not an IP address.")


def _owner(email):
    email = email.strip().lower()
    validate_email(email)
    User = get_user_model()
    matches = list(User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email))[:2])
    if len(matches) > 1:
        raise ValidationError("This email matches multiple accounts. Resolve the accounts before inviting this owner.")
    if matches:
        user = matches[0]
        if not user.is_active:
            raise ValidationError("This owner account is inactive. Review it before granting access.")
        return user
    if len(email) > User._meta.get_field("username").max_length:
        raise ValidationError("Use an owner email of at most 150 characters.")
    user = User(username=email, email=email)
    user.set_unusable_password()
    user.save()
    return user


def _invitation(tenant, user, actor):
    raw = secrets.token_urlsafe(32)
    with tenant_context(tenant):
        OwnerInvitation.objects.filter(user=user, accepted_at__isnull=True, revoked_at__isnull=True).update(revoked_at=timezone.now())
        invitation = OwnerInvitation.objects.create(user=user, email=user.email or user.username,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=timezone.now()+timedelta(days=7))
        PlatformAuditEvent.objects.create(actor=actor, action="owner_invited", details={"user_id": user.pk, "invitation_id": invitation.pk})
    return invitation, raw


@transaction.atomic
def provision_kitchen(*, actor, name, slug, owner_email, preset):
    require_operator(actor)
    slug = normalized_slug(slug)
    if not name.strip() or len(name.strip()) > 120:
        raise ValidationError("Enter a kitchen name of at most 120 characters.")
    if preset not in preset_names():
        raise ValidationError("Choose a supported kitchen preset.")
    if Tenant.objects.filter(slug=slug).exists():
        raise ValidationError("That kitchen address is already taken.")
    domain = f"{slug}.{base_domain()}" if base_domain() else ""
    if domain == getattr(settings, "PLATFORM_HOST", "") or (domain and TenantDomain.objects.filter(hostname=domain).exists()):
        raise ValidationError("That hostname is already reserved.")
    user = _owner(owner_email)
    tenant = Tenant.objects.create(name=name.strip(), slug=slug, primary_domain=domain, status=TenantStatus.PROVISIONING)
    if domain:
        TenantDomain.objects.create(tenant=tenant, hostname=domain, is_primary=True)
    apply_preset(tenant, preset)
    TenantConfig.objects.filter(tenant=tenant).update(brand_name=tenant.name)
    with tenant_context(tenant):
        TenantUser.objects.create(user=user, role="owner")
        PlatformAuditEvent.objects.create(actor=actor, action="kitchen_created", details={"preset": preset, "domain": domain})
    invitation, token = _invitation(tenant, user, actor)
    return tenant, invitation, token


@transaction.atomic
def invite_owner(*, actor, tenant, email, role="owner"):
    require_operator(actor)
    if role not in ("owner", "manager", "staff"):
        raise ValidationError("Choose a valid kitchen role.")
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    user = _owner(email)
    with tenant_context(tenant):
        membership, _ = TenantUser.objects.get_or_create(user=user, defaults={"role": role})
        if membership.role != role:
            membership.role = role
            membership.save(update_fields=["role"])
    return _invitation(tenant, user, actor)


def invitation_for_token(token):
    if not isinstance(token, str) or not 30 <= len(token) <= 100:
        return None
    return OwnerInvitation.all_tenants.select_related("user", "tenant").filter(
        token_hash=hashlib.sha256(token.encode()).hexdigest(), accepted_at__isnull=True,
        revoked_at__isnull=True, expires_at__gt=timezone.now()).first()


@transaction.atomic
def accept_invitation(*, token, password=None, signed_in_user=None):
    invitation = invitation_for_token(token)
    if not invitation:
        raise ValidationError("This invitation expired, was replaced or has already been used.")
    with tenant_context(invitation.tenant):
        invitation = OwnerInvitation.objects.select_for_update().get(pk=invitation.pk)
        if invitation.accepted_at or invitation.revoked_at or invitation.expires_at <= timezone.now():
            raise ValidationError("This invitation is no longer valid.")
        user = get_user_model().objects.select_for_update().get(pk=invitation.user_id)
        if not user.is_active or not TenantUser.objects.filter(user=user).exists():
            raise ValidationError("This invitation no longer grants access.")
        activated = not user.has_usable_password()
        if activated:
            from django.contrib.auth.password_validation import validate_password
            validate_password(password or "", user=user)
            user.set_password(password)
            user.save(update_fields=["password"])
        elif not signed_in_user or signed_in_user.pk != user.pk:
            raise ValidationError("Sign in with the invited account to accept this invitation.")
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=["accepted_at"])
        PlatformAuditEvent.objects.create(actor=user, action="invitation_accepted", details={"invitation_id": invitation.pk})
    return user, activated


@transaction.atomic
def change_kitchen_status(*, actor, tenant, status):
    require_operator(actor)
    if status not in (TenantStatus.PROVISIONING, TenantStatus.ACTIVE, TenantStatus.SUSPENDED):
        raise ValidationError("Choose setup, active or suspended ordering.")
    tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
    before = tenant.status
    if before != status:
        tenant.status = status
        tenant.save(update_fields=["status"])
        with tenant_context(tenant):
            PlatformAuditEvent.objects.create(actor=actor, action="status_changed", details={"from": before, "to": status})
    return tenant


def onboarding_progress(tenant):
    from apps.catalog.models import MenuItem
    from apps.delivery.models import DeliveryZone
    with tenant_context(tenant):
        config = tenant.config
        profile = tenant.billing_profile
        return {
            "identity": bool(config.brand_name and config.support_phone),
            "menu": MenuItem.objects.filter(active=True).exists(),
            "delivery": DeliveryZone.objects.filter(active=True).exists(),
            "billing": bool(profile.legal_name and profile.address and profile.fssai_no),
            "owner": TenantUser.objects.filter(role="owner", user__is_active=True).exclude(user__password__startswith="!").exists(),
        }


@transaction.atomic
def set_kitchen_features(*, actor, tenant, values):
    require_operator(actor)
    if set(values) != {"website_ordering", "snacks_courier"} or any(type(v) is not bool for v in values.values()):
        raise ValidationError("Choose valid website feature settings.")
    config = TenantConfig.objects.select_for_update().get(tenant=tenant)
    config.features = {**config.features, **values}
    config.full_clean()
    config.save(update_fields=["features"])
    with tenant_context(tenant):
        PlatformAuditEvent.objects.create(actor=actor, action="website_features_updated", details=values)
