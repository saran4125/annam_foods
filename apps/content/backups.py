"""Private, store-scoped image export. No network calls or database changes."""
import json
import shutil
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.staticfiles import finders
from django.utils import timezone

from apps.tenancy.context import tenant_context
from .storage import BILL_LOGO, LEGACY_BILL_LOGO, media_storage

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.avif', '.ico'}


def can_export_media(user, tenant):
    from apps.tenancy.models import TenantUser, TenantUserRole
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    with tenant_context(tenant):
        return TenantUser.objects.filter(user=user, role=TenantUserRole.OWNER).exists()


def build_media_backup(tenant):
    from apps.catalog.models import MenuCategory, MenuItem
    from .models import Banner, StorefrontImage

    output = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
    storage = media_storage()
    sources, external, missing = {}, set(), []

    def add_name(name, backend=storage):
        if not name:
            return
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name
                or path.suffix.lower() not in IMAGE_EXTENSIONS):
            missing.append({'path': 'Invalid image path', 'reason': 'Not exported'})
            return
        if path.parts[0] == 'website' and (len(path.parts) < 3 or path.parts[1] != str(tenant.pk)):
            missing.append({'path': 'Website library image', 'reason': 'Not owned by this store'})
            return
        sources.setdefault(str(path), backend)

    def image_url(value):
        if value == LEGACY_BILL_LOGO:
            value = BILL_LOGO
        try:
            parsed = urlsplit(value)
        except ValueError:
            missing.append({'path': 'Invalid image URL', 'reason': 'Not exported'})
            return
        if parsed.netloc:
            external.add(parsed._replace(query='', fragment='').geturl())
        elif parsed.path.startswith(('/media/', 'media/')):
            add_name(unquote(parsed.path.lstrip('/').removeprefix('media/')))
        elif value and not parsed.path.startswith('/platform/assets/'):
            missing.append({'path': parsed.path, 'reason': 'Image is outside the media folder'})

    def scan(value, parent=''):
        if isinstance(value, dict):
            for key, child in value.items():
                scan(child, 'image' if parent == 'images' else key)
        elif isinstance(value, list):
            for child in value:
                scan(child, parent)
        elif isinstance(value, str) and parent in {'image', 'logo_url', 'billing_logo_url'}:
            image_url(value)

    try:
        with tenant_context(tenant), ZipFile(output, 'w', ZIP_DEFLATED, allowZip64=True) as archive:
            for model in (MenuItem, MenuCategory, Banner):
                for record in model.objects.exclude(image='').iterator():
                    add_name(record.image.name, record.image.storage)
            config = tenant.config
            for value in (config.theme, config.home_sections, config.storefront_design):
                scan(value)

            saved = []
            for name, backend in sorted(sources.items()):
                # Read a complete file before adding it, so a failed read cannot
                # leave a silently truncated image in the archive.
                with SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode='w+b') as buffer:
                    try:
                        if backend.exists(name):
                            source = backend.open(name, 'rb')
                        else:
                            bundled = finders.find('public-media/' + name)
                            if not bundled:
                                raise FileNotFoundError(name)
                            source = open(bundled, 'rb')
                        with source:
                            shutil.copyfileobj(source, buffer)
                        buffer.seek(0)
                        with archive.open('media/' + name, 'w', force_zip64=True) as target:
                            shutil.copyfileobj(buffer, target)
                        saved.append('media/' + name)
                    except OSError:
                        missing.append({'path': name, 'reason': 'File missing or unreadable'})

            # Legacy editor files may be recoverable from their database copy.
            # This export includes drafts too, hence owner-only authorization.
            for image in StorefrontImage.objects.iterator():
                extension = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}.get(image.content_type)
                if not extension:
                    missing.append({'path': f'website/{image.pk}', 'reason': 'Unsupported image format'})
                    continue
                name = f'website/{tenant.pk}/{image.pk}{extension}'
                if 'media/' + name in saved:
                    continue
                if storage.exists(name):
                    with storage.open(name, 'rb') as source, archive.open('media/' + name, 'w', force_zip64=True) as target:
                        shutil.copyfileobj(source, target)
                else:
                    archive.writestr('media/' + name, bytes(image.data))
                saved.append('media/' + name)

            report = {'store': tenant.slug, 'created_at': timezone.now().isoformat(),
                      'image_count': len(saved), 'files': saved, 'missing_files': missing,
                      'external_images_not_included': sorted(external),
                      'scope': 'Store-referenced product, category, banner, logo and saved website images; '
                               'unreferenced files and other stores are excluded.'}
            archive.writestr('backup-report.json', json.dumps(report, indent=2))
            archive.writestr('README.txt',
                'Extract media/ as your image folder. Check backup-report.json for missing files '
                'and external images before treating this as a complete backup. This ZIP does not '
                'contain the database, environment settings, credentials, bills or WhatsApp attachments.\n')
        output.seek(0)
        return output, report
    except Exception:
        output.close()
        raise
