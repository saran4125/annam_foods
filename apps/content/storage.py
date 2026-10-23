"""Materialize recoverable image sources as files in MEDIA_ROOT.

Legacy editor bytes remain a recovery copy. Draft image files are served only
through the existing authenticated image endpoint, never the public media view.
"""
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

LEGACY_BILL_LOGO = '/static/branding/annam-bill-logo.png'
BILL_LOGO = '/media/brand/annam-bill-logo.png'


def media_storage():
    return FileSystemStorage(location=settings.MEDIA_ROOT, base_url='/media/')


def write_missing(name, data):
    storage = media_storage()
    if not storage.exists(name):
        saved = storage.save(name, ContentFile(data))
        # Another worker may have written the same deterministic file first.
        if saved != name:
            storage.delete(saved)
    return name


def editor_image_file(image):
    extension = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}[image.content_type]
    name = f'website/{image.tenant_id}/{image.pk}{extension}'
    write_missing(name, bytes(image.data))
    return media_storage().open(name, 'rb')


def restore_bundled_media():
    from django.contrib.staticfiles import finders
    restored = 0
    for finder in finders.get_finders():
        for name, storage in finder.list([]):
            if name.startswith('public-media/') and name.lower().endswith(
                    ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.avif')):
                relative = name.removeprefix('public-media/')
                if not media_storage().exists(relative):
                    with storage.open(name, 'rb') as source:
                        write_missing(relative, source.read())
                    restored += 1
    return restored
