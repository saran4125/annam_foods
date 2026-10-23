"""Public published website images; private draft images remain kitchen-scoped."""

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control

from apps.owner.access import can_manage
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant
from .models import StorefrontImage
from .services import storefront_image_url
from .storage import editor_image_file


def storefront_image(request, slug, pk):
    kitchen = get_object_or_404(Tenant, slug=slug)
    with tenant_context(kitchen):
        image = get_object_or_404(StorefrontImage.objects, tenant=kitchen, pk=pk)
        published = (kitchen.config.storefront_design or {}).get('published', {})
        is_public = storefront_image_url(kitchen, image) in published.get('images', {}).values()
        if not is_public and not can_manage(request.user, kitchen):
            raise Http404
    response = FileResponse(editor_image_file(image), content_type=image.content_type)
    response['X-Content-Type-Options'] = 'nosniff'
    patch_cache_control(response, private=True, no_store=True)
    return response
