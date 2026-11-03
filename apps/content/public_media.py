"""Apply checksum-verified public originals without altering commerce records."""
import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.catalog.models import MenuCategory, MenuItem
from apps.tenancy.context import tenant_context
from .storage import media_storage, write_missing
from .models import Banner

PATH = re.compile(r'^(catalog|categories|brand|site)/[a-f0-9]{32}\.(jpg|png|gif|webp|avif|ico)$')


def verified_assets():
    manifest = Path(settings.BASE_DIR) / 'deploy/annam_public_media.json'
    if not manifest.is_file():
        return {}
    assets = {}
    root = (Path(settings.BASE_DIR) / 'media').resolve()
    for asset in json.loads(manifest.read_text())['assets'].values():
        name = asset.get('path', '')
        if asset.get('status') != 'downloaded' or not PATH.fullmatch(name):
            continue
        file = root / name
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(root):
            continue
        if hashlib.sha256(file.read_bytes()).hexdigest() == asset.get('sha256'):
            assets[asset['url']] = asset
    return assets


def restore_originals(assets=None):
    assets = verified_assets() if assets is None else assets
    root = Path(settings.BASE_DIR) / 'media'
    for asset in assets.values():
        data = (root / asset['path']).read_bytes()
        write_missing(asset['path'], data)
        for alias in asset.get('legacy_paths', []):
            if re.fullmatch(r'(menu|categories|brand)/[a-f0-9]{24}\.(jpg|jpeg|png|webp|gif|avif|ico)', alias):
                write_missing(alias, data)
    return len(assets)


def apply_originals(tenant):
    assets = verified_assets()
    restore_originals(assets)
    match_file = Path(settings.BASE_DIR) / 'deploy/annam_public_image_matches.json'
    if not match_file.is_file():
        return {'verified_files': len(assets), 'updated': 0}
    payload = json.loads(match_file.read_text())
    if payload.get('tenant') != tenant.slug:
        return {'verified_files': len(assets), 'updated': 0}
    matches = payload['matches']
    updated = 0
    recovered_paths = {a['path'] for a in assets.values()}
    with tenant_context(tenant), transaction.atomic():
        for match in matches:
            asset = assets.get(match['url'])
            if not asset:
                continue
            if match['kind'] == 'product':
                rows = MenuItem.objects.select_for_update().filter(retailer_id=match['source_id'])
            elif match['kind'] == 'banner':
                rows = Banner.objects.select_for_update().filter(title=match['title'])
            else:
                rows = MenuCategory.objects.select_for_update().filter(slug=match['slug'])
            for row in rows:
                current = row.image.name or ''
                if current == asset['path']:
                    continue
                # Preserve staff-uploaded working photos. Restore missing originals
                # and refresh previously recovered public photos only.
                if current and current != asset['url'] and current not in recovered_paths and media_storage().exists(current):
                    continue
                row.image = asset['path']
                row.save(update_fields=['image'])
                updated += 1
    return {'verified_files': len(assets), 'updated': updated}
