"""Resolve the tenant from the request's hostname."""
from django.conf import settings
from django.http import HttpResponseNotFound
from django.utils import timezone

from .context import reset_current_tenant, set_current_tenant
from .models import TenantDomain


class TenantMiddleware:
    """Maps Host -> Tenant and holds it for the life of the request.

    Requests to the platform host (the SEER super admin) carry no tenant, which
    is correct: platform code must opt into `all_tenants()` explicitly rather
    than inheriting a tenant by accident.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        platform_host = getattr(settings, "PLATFORM_HOST", "").lower()
        request.tenant = None
        token = None
        previous_timezone = timezone.get_current_timezone()

        if host != platform_host and request.path != "/healthz":
            domain = (
                TenantDomain.objects.select_related("tenant", "tenant__config")
                .filter(hostname=host)
                .first()
            )
            if domain is None:
                # An unknown hostname is not a tenant. Say so plainly rather
                # than falling through and serving someone else's kitchen.
                return HttpResponseNotFound(
                    "No kitchen is configured for this address."
                )
            request.tenant = domain.tenant
            token = set_current_tenant(domain.tenant)
            # FIX-10: a kitchen's clock is its own. Cutoffs, menus and campaign
            # windows must agree at local midnight, never at the server's.
            config = getattr(domain.tenant, "config", None)
            if config is not None and config.timezone:
                timezone.activate(config.timezone)

        try:
            response = self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)
            timezone.activate(previous_timezone)
        return response


class PlatformAdminGuard:
    """`/admin/` belongs to the platform host only (FIX-11).

    A tenant's back-office is a `/manage/` area owned by the kitchen's own
    membership rules — not Django's unscoped admin. Until that exists, vendor
    admin must not be reachable behind a customer's hostname, where it would
    impersonate a kitchen tool rather than the platform's.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        platform_host = getattr(settings, "PLATFORM_HOST", "").lower()
        if host != platform_host and request.path.startswith("/admin/"):
            return HttpResponseNotFound("Not on this host.")
        return self.get_response(request)
