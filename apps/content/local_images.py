"""Copy configured Annam image links into media without rewriting failed links."""
import hashlib
from io import BytesIO
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image
from django.contrib.staticfiles import finders
from django.db import transaction

from .storage import BILL_LOGO, LEGACY_BILL_LOGO, media_storage, write_missing

MAX_IMAGE_BYTES = 12 * 1024 * 1024
IMAGE_HOSTS = {'cdn.commmerce.com', 'www.annamfood.in', 'annamfood.in'}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_image_url(url, tenant_id, *, download=False):
    if url == LEGACY_BILL_LOGO:
        return BILL_LOGO
    if url.startswith('/static/'):
        from pathlib import Path
        source = finders.find(url.removeprefix('/static/'))
        if not source:
            raise ValueError('Static image file is missing')
        data = Path(source).read_bytes()
    elif url.startswith(('https://', 'http://', '//')):
        if not download:
            raise ValueError('External image requires --download')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in IMAGE_HOSTS
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise ValueError('Image host is not an approved Annam image source')
        # Never follow a redirect into an unapproved host or private network.
        request = Request(url, headers={'User-Agent': 'Annam-media-import/1.0'})
        with build_opener(NoRedirect()).open(request, timeout=25) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
    else:
        return url
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Image exceeds the 12 MB import limit')
    with Image.open(BytesIO(data)) as image:
        extension = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'GIF': '.gif'}.get(image.format)
        if not extension or image.width * image.height > 40_000_000:
            raise ValueError('Unsupported image format or dimensions')
        image.verify()
    name = f'imported/{tenant_id}/{hashlib.sha256(data).hexdigest()}{extension}'
    write_missing(name, data)
    return media_storage().url(name)


def localize_store_images(tenant, *, download=False):
    from apps.tenancy.context import tenant_context
    from apps.tenancy.models import TenantConfig
    from .models import StorefrontImage
    from .storage import editor_image_file

    failures, cache = [], {}

    def convert(url):
        if url not in cache:
            try:
                cache[url] = local_image_url(url, tenant.pk, download=download)
            except Exception as exc:
                # Keep the working original on a failed download; never save a broken replacement.
                failures.append((url, type(exc).__name__))
                cache[url] = url
        return cache[url]

    def walk(value, parent=''):
        if isinstance(value, dict):
            return {key: walk(item, key if parent != 'images' else 'image')
                    for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item, parent) for item in value]
        if isinstance(value, str) and parent in {'image', 'logo_url', 'billing_logo_url'}:
            return convert(value)
        return value

    with tenant_context(tenant):
        for image in StorefrontImage.objects.iterator():
            with editor_image_file(image):
                pass
        # Lock before reading so an admin's simultaneous content edits are preserved.
        with transaction.atomic():
            config = TenantConfig.objects.select_for_update().get(tenant=tenant)
            for field in ('theme', 'home_sections', 'storefront_design'):
                setattr(config, field, walk(getattr(config, field)))
            config.save(update_fields=['theme', 'home_sections', 'storefront_design'])
    return failures
