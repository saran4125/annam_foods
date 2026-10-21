"""Serve public uploads, with bundled recovery files for imported catalog media.

A bundled file has the same relative path under static/public-media/. It is a
fallback only: an owner's uploaded replacement always takes precedence. This
keeps selected imported assets available on hosts with an ephemeral media disk,
without a network download or a database rewrite on each deployment.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import Http404
from django.views.static import serve


def public_media(request, path):
    if not settings.DEBUG and not getattr(settings, "SERVE_MEDIA", False):
        raise Http404("Public media is served by external storage.")
    # Validate before consulting the static finder: recovery must stay inside
    # its public-media namespace, including when the upload does not exist.
    if path.startswith("/") or ".." in path.split("/") or "\\" in path:
        raise Http404("Invalid public media path.")
    try:
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    except Http404:
        bundled = finders.find("public-media/" + path)
        if not bundled:
            raise
        asset = Path(bundled)
        return serve(request, asset.name, document_root=asset.parent)
