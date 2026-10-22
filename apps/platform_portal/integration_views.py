"""Stable integration addresses and safe redirects for retired SEER bookmarks.

There is no platform UI here. Existing published assets and provider callbacks
keep their URLs so removing the portal does not disrupt the Annam storefront.
"""
from urllib.parse import urlencode, urlsplit, unquote

from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe


@csrf_exempt
def tenant_meta_webhook(request, slug):
    from apps.messaging.webhooks import meta_webhook
    return meta_webhook(request)


@csrf_exempt
def tenant_n8n_webhook(request, slug):
    from apps.messaging.webhooks import n8n_sync
    return n8n_sync(request)


def legacy_target(request, value):
    """Translate only this host's old workspace links into local application paths."""
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return None
    try:
        path = urlsplit(value).path
    except ValueError:
        return None
    # Do not normalize traversal into a different application or external URL.
    decoded = unquote(path)
    if "\\" in decoded or "//" in decoded or any(ord(char) < 32 for char in decoded) or any(part in (".", "..") for part in decoded.split("/")):
        return None
    prefix = f"/platform/workspaces/{tenant.slug}/"
    if not path.startswith(prefix):
        return None
    suffix = path[len(prefix):]
    if suffix.startswith("manage/"):
        if suffix.startswith("manage/appearance"):
            return None
        return "/" + suffix
    if suffix.startswith("billing/"):
        return "/" + suffix
    if suffix.startswith("preview/"):
        return "/" + suffix[len("preview/"):]
    if not suffix:
        return "/manage/"
    return None


@require_safe
@never_cache
def retired_page(request, path=""):
    """Old GET bookmarks redirect; retired mutations are never replayed."""
    if path in ("", "login/", "about/"):
        destination = "/manage/login/"
        target = legacy_target(request, request.GET.get("next", ""))
        if target and target.startswith("/manage/"):
            from apps.owner.access import kitchen_login_target
            target = kitchen_login_target(request, target)
            destination += "?" + urlencode({"next": target})
        return redirect(destination)
    if path.startswith("workspaces/"):
        destination = legacy_target(request, "/platform/" + path)
        if destination:
            # Discard old preview/editor query parameters, preserve useful list filters.
            query = request.GET.copy()
            query.pop("design", None)
            if query:
                destination += "?" + query.urlencode()
            return redirect(destination)
    raise Http404
