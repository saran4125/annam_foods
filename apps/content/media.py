"""Serve public uploads, with bundled recovery files for imported catalog media.

A bundled file has the same relative path under static/public-media/. It is
copied into MEDIA_ROOT when missing; an owner's uploaded replacement always
takes precedence. Responses always read the file in the media folder.
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
    if path.split('/')[0] == 'website':
        raise Http404("Website library images require their access-controlled endpoint.")
    try:
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    except Http404:
        bundled = finders.find("public-media/" + path)
        if not bundled:
            raise
        from .storage import write_missing
        asset = Path(bundled)
        if not asset.is_file():
            raise Http404("Not an image file.")
        write_missing(path, asset.read_bytes())
        return serve(request, path, document_root=settings.MEDIA_ROOT)
