"""Owner domain preparation, verification and explicit production cutover."""
import ipaddress
import re
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from apps.tenancy.context import tenant_context
from apps.tenancy.models import CustomDomain, Tenant, TenantDomain, TenantUser, PlatformAuditEvent
from . import domain_network as network


def require_domain_owner(user, tenant):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    if user.is_superuser:
        return
    with tenant_context(tenant):
        if not TenantUser.objects.filter(user=user, role="owner").exists():
            raise PermissionDenied("Only kitchen owners can manage website domains.")


def normalize_hostname(value):
    value = str(value).strip().rstrip(".").lower()
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("Enter a valid domain name.") from exc
    labels = value.split(".")
    if len(value) > 253 or len(labels) < 2 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels):
        raise ValidationError("Enter only the domain name, without https://, paths, ports or wildcards.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise ValidationError("Enter a domain name, not an IP address.")
    if labels[-1].isdigit() or value.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example", ".onrender.com")) or value == str(settings.PLATFORM_HOST).lower():
        raise ValidationError("Use your own public custom domain, not a platform or local testing hostname.")
    return value


def destination():
    target = str(settings.DOMAIN_CNAME_TARGET).strip().lower().rstrip(".")
    if not target:
        return ""
    # Provider-assigned onrender.com destinations are allowed here, not as claims.
    if len(target) > 253 or "." not in target or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in target.split(".")):
        raise ValidationError("The platform's DNS destination needs administrator configuration.")
    return target


def _audit(tenant, actor, action, hostname):
    with tenant_context(tenant):
        PlatformAuditEvent.objects.create(actor=actor, action=action, details={"hostname": hostname})


@transaction.atomic
def add_domain(*, actor, tenant, hostname):
    require_domain_owner(actor, tenant)
    hostname = normalize_hostname(hostname)
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    if TenantDomain.objects.filter(hostname=hostname).exists() or CustomDomain.all_tenants.filter(hostname=hostname).exists():
        raise ValidationError("This domain is already assigned or has a pending connection. Contact your platform administrator if it belongs to you.")
    with tenant_context(tenant):
        if CustomDomain.objects.count() >= 10:
            raise ValidationError("You can prepare up to ten custom domains per kitchen.")
        domain = CustomDomain.objects.create(hostname=hostname, verification_token="seerkitchen=" + secrets.token_hex(24))
    _audit(tenant, actor, "domain_added", hostname)
    return domain


def _owned_domain(tenant, pk):
    domain = CustomDomain.objects.select_for_update().filter(pk=pk, tenant=tenant).first()
    if domain is None:
        raise ValidationError("This domain connection changed. Reload the page.")
    return domain


@transaction.atomic
def check_domain(*, actor, tenant, pk, connect=False):
    require_domain_owner(actor, tenant)
    with tenant_context(tenant):
        domain = _owned_domain(tenant, pk)
        if domain.checked_at and domain.checked_at > timezone.now() - timedelta(seconds=15):
            raise ValidationError("Please wait 15 seconds before checking this domain again.")
        domain.checked_at = timezone.now()
        domain.dns_verified_at = None
        was_live = bool(domain.mapping_id)
        try:
            if domain.verification_token not in network.dns_records(domain.txt_name, "TXT"):
                domain.ownership_verified_at = None
                domain.dns_verified_at = None
                raise network.DomainCheckError("The ownership TXT record was not found yet. Check its name and value, then try again after DNS updates.")
            domain.ownership_verified_at = timezone.now()
            domain.status = "dns_pending"
            target = destination()
            if not target:
                raise network.DomainCheckError("Ownership verified. Your platform administrator needs to configure the hosting destination before connection.")
            addresses = network.check_destination(domain.hostname, target, settings.DOMAIN_APEX_IPV4)
            domain.dns_verified_at = timezone.now()
            domain.status = "active" if was_live and domain.tls_verified_at and not connect else "hosting_pending"
            if not settings.DOMAIN_CONNECTIONS_ENABLED:
                domain.detail = "DNS verified. Production connection is not enabled yet; your current storefront stays unchanged."
            elif not connect and not domain.connection_requested_at:
                domain.detail = "DNS verified. Choose Connect website when you are ready for production."
            else:
                if not domain.connection_requested_at:
                    domain.connection_requested_at = timezone.now()
                    _audit(tenant, actor, "domain_connection_requested", domain.hostname)
                # Persist the verified claim for the edge/TLS proof request, which
                # runs on a separate connection. Finish activation in a second phase.
                domain.detail = "Ownership and DNS verified. Hosting and HTTPS will be checked next."
        except network.DomainCheckError as exc:
            domain.detail = str(exc)
            domain.status = "attention" if was_live else ("dns_pending" if domain.ownership_verified_at else "ownership_pending")
        domain.save()
    return domain


def connect_domain(*, actor, tenant, pk):
    # DNS verification commits before the HTTPS challenge can reach this app.
    domain = check_domain(actor=actor, tenant=tenant, pk=pk, connect=True)
    if not settings.DOMAIN_CONNECTIONS_ENABLED or domain.status != "hosting_pending" or not domain.connection_requested_at:
        return domain
    try:
        if settings.DOMAIN_HOSTING_PROVIDER == "render":
            provider_id = network.register_render(domain.hostname, domain.provider_id)
            with tenant_context(tenant):
                CustomDomain.objects.filter(pk=domain.pk).update(provider_id=provider_id)
            network.verify_render(provider_id)
        elif settings.DOMAIN_HOSTING_PROVIDER not in ("caddy", "manual"):
            raise network.DomainCheckError("The platform hosting provider needs administrator configuration.")
        # Re-resolve and pin only public, correctly pointed destinations.
        addresses = network.check_destination(domain.hostname, destination(), settings.DOMAIN_APEX_IPV4)
        network.check_https(domain.hostname, domain.verification_token, addresses)
    except network.DomainCheckError as exc:
        with tenant_context(tenant):
            CustomDomain.objects.filter(pk=domain.pk).update(detail=str(exc), status="attention" if domain.mapping_id else "hosting_pending", tls_verified_at=None)
        try:
            domain.refresh_from_db()
        except CustomDomain.DoesNotExist as exc:
            raise ValidationError("This domain connection was removed. Reload the page.") from exc
        return domain
    with transaction.atomic(), tenant_context(tenant):
        domain = _owned_domain(tenant, pk)
        Tenant.objects.select_for_update().get(pk=tenant.pk)
        # A disconnect or replacement during network I/O cannot resurrect routing.
        if not domain.connection_requested_at or not domain.ownership_verified_at:
            raise ValidationError("The domain connection changed. Reload the page.")
        mapping, _ = TenantDomain.objects.get_or_create(hostname=domain.hostname, defaults={"tenant": tenant})
        if mapping.tenant_id != tenant.pk:
            raise ValidationError("This domain is already assigned to another kitchen.")
        domain.mapping = mapping
        domain.status = "active"
        domain.tls_verified_at = timezone.now()
        domain.detail = "Connected securely. You can now make this your primary website address."
        domain.save()
        _audit(tenant, actor, "domain_connected", domain.hostname)
    return domain


@transaction.atomic
def make_primary(*, actor, tenant, pk):
    require_domain_owner(actor, tenant)
    if not settings.DOMAIN_CONNECTIONS_ENABLED:
        raise ValidationError("Production domain connections are not enabled yet.")
    with tenant_context(tenant):
        domain = _owned_domain(tenant, pk)
        if domain.status != "active" or not domain.mapping_id or not domain.tls_verified_at or domain.tls_verified_at < timezone.now()-timedelta(days=1):
            raise ValidationError("Check the domain connection and HTTPS before making it primary.")
        Tenant.objects.select_for_update().get(pk=tenant.pk)
        if domain.mapping.tenant_id != tenant.pk:
            raise ValidationError("The domain mapping needs administrator review.")
        TenantDomain.objects.filter(tenant=tenant).update(is_primary=False)
        TenantDomain.objects.filter(pk=domain.mapping_id, tenant=tenant).update(is_primary=True)
        Tenant.objects.filter(pk=tenant.pk).update(primary_domain=domain.hostname)
        _audit(tenant, actor, "domain_primary_changed", domain.hostname)


def remove_domain(*, actor, tenant, pk):
    require_domain_owner(actor, tenant)
    with transaction.atomic(), tenant_context(tenant):
        domain = _owned_domain(tenant, pk)
        kitchen = Tenant.objects.select_for_update().get(pk=tenant.pk)
        if domain.mapping_id and (domain.mapping.is_primary or kitchen.primary_domain == domain.hostname):
            raise ValidationError("Choose another connected primary domain before removing this one.")
        if domain.provider_id:
            network.remove_render(domain.provider_id)
        if domain.mapping_id:
            TenantDomain.objects.filter(pk=domain.mapping_id, tenant=tenant).delete()
        hostname = domain.hostname
        domain.delete()
        _audit(tenant, actor, "domain_removed", hostname)
