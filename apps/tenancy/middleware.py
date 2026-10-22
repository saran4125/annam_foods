"""Resolve the tenant from the request's hostname."""
from django.conf import settings
from django.http import HttpResponseNotFound
from django.http.request import split_domain_port, validate_host
import re
from django.utils import timezone

from .context import reset_current_tenant, set_current_tenant
from .models import TenantDomain, Tenant, CustomDomain


class ManagedDomainHostMiddleware:
    """Retain existing connected hosts; pending domain claims no longer admit traffic."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        raw = request._get_raw_host()
        host, port = split_domain_port(raw)
        if host and not validate_host(host, settings.ALLOWED_HOSTS) and port in ("", "80", "443"):
            approved = CustomDomain.all_tenants.filter(hostname=host, mapping__isnull=False).exists()
            store_slug = getattr(settings, "STORE_SLUG", "")
            if store_slug:
                approved = CustomDomain.all_tenants.filter(hostname=host, mapping__isnull=False, tenant__slug=store_slug).exists()
            if approved:
                request.get_host = lambda: raw
        return self.get_response(request)


class TenantMiddleware:
    """Resolve the store by hostname; preserve scoped data without a platform UI."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        request.tenant = None
        token = None
        previous_timezone = timezone.get_current_timezone()

        store_slug = getattr(settings, "STORE_SLUG", "")
        # Provider callbacks on the former platform host keep working. They are
        # exact, separately authenticated routes, never a browser tenant selector.
        callback = re.fullmatch(r"/platform/webhooks/([a-z0-9-]+)/(?:razorpay/(?:test|live)/|whatsapp/(?:n8n/)?)", request.path)
        selected = None
        if callback and host == getattr(settings, "PLATFORM_HOST", "").lower():
            stores = Tenant.objects.select_related("config").filter(slug=callback.group(1))
            if store_slug:
                stores = stores.filter(slug=store_slug)
            selected = stores.first()
            if selected is None:
                return HttpResponseNotFound("Not found.")
        elif request.path != "/healthz":
            domains = TenantDomain.objects.select_related("tenant", "tenant__config").filter(hostname=host)
            if store_slug:
                domains = domains.filter(tenant__slug=store_slug)
            domain = domains.first()
            if domain is None:
                return HttpResponseNotFound("No store is configured for this address.")
            selected = domain.tenant
        integration = re.match(r"^/platform/(?:webhooks|assets)/([a-z0-9-]+)(?:/|$)", request.path)
        if integration and (selected is None or integration.group(1) != selected.slug):
            return HttpResponseNotFound("Not found.")
        if selected:
            request.tenant = selected
            token = set_current_tenant(selected)
            config = getattr(selected, "config", None)
            if config is not None and config.timezone:
                timezone.activate(config.timezone)

        try:
            response = self.get_response(request)
        finally:
            if token is not None:
                reset_current_tenant(token)
            timezone.activate(previous_timezone)
        return response
