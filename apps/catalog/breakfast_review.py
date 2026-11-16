"""Apply the owner's breakfast screenshots once; dates remain staff controlled."""
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant
from .models import CatalogSyncRun, MenuCategory, MenuItem


@transaction.atomic
def sync_breakfast(tenant, apply=False):
    raw = (Path(settings.BASE_DIR) / 'deploy/annam_breakfast_review_20261116.json').read_bytes()
    data = json.loads(raw)
    if tenant.slug != data['tenant_slug']:
        raise ValidationError('The breakfast review belongs to a different store.')
    digest = hashlib.sha256(raw).hexdigest()
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    with tenant_context(tenant):
        previous = CatalogSyncRun.objects.filter(version=data['version']).first()
        if previous:
            if previous.digest != digest:
                raise ValidationError('Breakfast review changed after application; use a new version.')
            return {'already_applied': True, 'created': [], 'updated': []}
        category, _ = MenuCategory.objects.get_or_create(slug='breakfast', defaults={'name': 'Breakfast'})
        report = {'created': [], 'updated': [], 'source': data['source'], 'applied': apply}
        for row in data['items']:
            item = MenuItem.objects.filter(retailer_id=row['retailer_id']).first()
            created = item is None
            if item and item.fulfilment != 'scheduled':
                raise ValidationError(f'{row["name"]} conflicts with a shop product.')
            if created:
                item = MenuItem(retailer_id=row['retailer_id'], fulfilment='scheduled', image=row['image'])
            item.name = row['name']
            item.price = row['price']
            item.in_stock = row['in_stock']
            item.active = True
            item.category = category
            item.save()
            report['created' if created else 'updated'].append(row['name'])
        if apply:
            CatalogSyncRun.objects.create(version=data['version'], digest=digest, report=report)
        else:
            transaction.set_rollback(True)
        return report
