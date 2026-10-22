"""Who may use a kitchen's owner backend.

The backend lives on the kitchen's own domain (/manage/). Access needs a
login AND a TenantUser membership for *this* kitchen; being staff somewhere
else, or logged in as a customer, is not enough. Platform superusers may
enter any kitchen, as they can through the super admin.
"""
from functools import wraps
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse

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
            return redirect(reverse("owner:login") + "?" + urlencode({"next": request.get_full_path()}))
        if not can_manage(request.user, tenant):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def kitchen_login_target(request, target):
    """Accept only local management destinations, with no traversal or login loop."""
    from urllib.parse import unquote, urlsplit
    from django.utils.http import url_has_allowed_host_and_scheme
    root = reverse("owner:dashboard")
    try:
        path = unquote(urlsplit(target).path)
    except ValueError:
        return root
    if (target.startswith(root) and path.startswith(root) and "\\" not in path
            and not any(segment in (".", "..") for segment in path.split("/"))
            and path.rstrip("/") not in (reverse("owner:login").rstrip("/"), reverse("owner:logout").rstrip("/"))
            and url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure())):
        return target
    return root
