"""Resolve the tenant from the request's hostname."""
from django.conf import settings
from django.http import HttpResponseNotFound
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode
import re
from django.utils import timezone

from .context import reset_current_tenant, set_current_tenant
from .models import TenantDomain, Tenant, TenantUser


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

        is_central = request.path == "/platform" or request.path.startswith("/platform/")
        domain = None
        if host != platform_host and request.path != "/healthz":
            domain = TenantDomain.objects.select_related("tenant", "tenant__config").filter(hostname=host).first()
            if domain is None:
                return HttpResponseNotFound("No kitchen is configured for this address.")
        selected = None
        if is_central:
            workspace = re.match(r"^/platform/workspaces/([a-z0-9-]+)/(manage|billing|preview)(?:/|$)", request.path)
            webhook = re.fullmatch(r"/platform/webhooks/([a-z0-9-]+)/whatsapp/(?:n8n/)?", request.path)
            if workspace:
                if not request.user.is_authenticated:
                    return redirect("/platform/login/?" + urlencode({"next": request.get_full_path()}))
                selected = Tenant.objects.select_related("config").filter(slug=workspace.group(1)).first()
                if selected is None or not request.user.is_active or not (request.user.is_superuser or TenantUser.all_tenants.filter(tenant=selected, user=request.user).exists()):
                    return HttpResponseNotFound("Workspace not found.")
                from apps.platform_portal.workspace_urls import workspace_urlconf
                request.urlconf = workspace_urlconf(selected.slug)
                request.workspace_slug = selected.slug
                request.workspace_preview_url = f"/platform/workspaces/{selected.slug}/preview/"
            elif webhook:
                # Public only for these exact signed/authenticated webhook paths.
                selected = Tenant.objects.select_related("config").filter(slug=webhook.group(1)).first()
                if selected is None:
                    return HttpResponseNotFound("Kitchen not found.")
        elif domain:
            selected = domain.tenant
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
