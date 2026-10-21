"""Who may use a kitchen's owner backend.

The backend lives on the kitchen's own domain (/manage/). Access needs a
login AND a TenantUser membership for *this* kitchen; being staff somewhere
else, or logged in as a customer, is not enough. Platform superusers may
enter any kitchen, as they can through the super admin.
"""
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect

from apps.tenancy.models import TenantUser


def can_manage(user, tenant) -> bool:
    if not user.is_authenticated or not user.is_active or tenant is None:
        return False
    if user.is_superuser:
        return True
    # TenantUser.objects is scoped to the current tenant by the middleware.
    return TenantUser.objects.filter(user=user, tenant=tenant).exists()


def owner_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            raise Http404
        if not request.user.is_authenticated:
            from apps.platform_portal.services import management_login_url
            return redirect(management_login_url(request, request.get_full_path()))
        if not can_manage(request.user, tenant):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
