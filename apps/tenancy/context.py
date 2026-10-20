"""Who are we serving right now?

The current tenant is held in a ContextVar rather than thread-local storage so
it behaves correctly under async views and background tasks. Middleware sets it
per request; tasks set it explicitly.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_current_tenant: ContextVar = ContextVar("current_tenant", default=None)
_unscoped: ContextVar = ContextVar("unscoped", default=False)


class TenantContextMissing(RuntimeError):
    """Raised when tenant-scoped data is queried with no tenant set.

    This is deliberately loud. A silent unscoped query is how one kitchen ends
    up reading another kitchen's orders, so the default is to fail.
    """


def get_current_tenant():
    return _current_tenant.get()


def set_current_tenant(tenant):
    """Set the tenant and return the token needed to restore the previous one."""
    return _current_tenant.set(tenant)


def reset_current_tenant(token):
    _current_tenant.reset(token)


def is_unscoped():
    return _unscoped.get()


@contextmanager
def tenant_context(tenant):
    """Run a block as a specific tenant.

    Use in management commands, background tasks and tests:

        with tenant_context(kitchen):
            Order.objects.count()
    """
    token = _current_tenant.set(tenant)
    try:
        yield tenant
    finally:
        _current_tenant.reset(token)


@contextmanager
def all_tenants():
    """Deliberately query across every tenant.

    Only for platform-level work: the SEER super admin, billing sweeps,
    scheduled jobs that iterate tenants. Never reachable from a tenant request.
    """
    token = _unscoped.set(True)
    try:
        yield
    finally:
        _unscoped.reset(token)


def tenant(request):
    """Template context processor: exposes `tenant` on every page."""
    tenant = get_current_tenant()
    return {"tenant": tenant,
            "tenant_home_url": getattr(request, "workspace_preview_url", "/"),
            "workspace_overview_url": f"/platform/workspaces/{request.workspace_slug}/" if hasattr(request, "workspace_slug") else ""}
