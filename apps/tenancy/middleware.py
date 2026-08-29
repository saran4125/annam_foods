"""Resolve the tenant from the request's hostname."""
from django.conf import settings
from django.http import HttpResponseNotFound

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
        request.tenant = None
        token = None

        if host != getattr(settings, "PLATFORM_HOST", "").lower():
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

        try:
            response = self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)
        return response
