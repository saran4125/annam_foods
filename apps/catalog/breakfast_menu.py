"""Schedule the reviewed breakfast once for the date requested by the owner."""
import hashlib
import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant, TenantConfig
from .daily_menus import save_daily_menu
from .models import CatalogSyncRun, MenuDay, MenuItem, Slot
from .services import resolve_menu


@transaction.atomic
def publish_reviewed_breakfast(tenant):
    root = Path(settings.BASE_DIR) / 'deploy'
    raw = (root / 'annam_breakfast_menu_20261116.json').read_bytes()
    plan = json.loads(raw)
    catalog = json.loads((root / 'annam_breakfast_review_20261116.json').read_text())
    if tenant.slug != plan['tenant_slug'] or tenant.slug != catalog['tenant_slug']:
        raise ValidationError('This breakfast menu belongs to a different store.')
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    config = TenantConfig.objects.select_for_update().get(tenant=tenant)
    if 'carry_forward_breakfast' not in config.features:
        config.features = {**config.features, 'carry_forward_breakfast': True}
        config.save(update_fields=['features'])
        tenant._state.fields_cache.pop('config', None)
    with tenant_context(tenant):
        if CatalogSyncRun.objects.filter(version=plan['version']).exists():
            return {'already_applied': True}
        on_date = date.fromisoformat(plan['date'])
        if timezone.localdate() != on_date:
            return {'skipped': f'The reviewed menu is for {on_date}; no other date was changed.'}
        slot = Slot.objects.get(key=plan['slot'])
        keys = [row['retailer_id'] for row in catalog['items']]
        products = list(MenuItem.objects.filter(retailer_id__in=keys, fulfilment='scheduled'))
        if {item.retailer_id for item in products} != set(keys):
            raise ValidationError('Apply the reviewed breakfast catalog before scheduling its dishes.')
        existing = {entry.item.pk for entry in resolve_menu(
            on_date, slot, include_unavailable=True, include_inactive=True) if entry.available}
        current = MenuDay.objects.filter(slot=slot, on_date=on_date).first()
        save_daily_menu(slot=slot, on_date=on_date,
                        item_ids=existing | {item.pk for item in products},
                        revision=current.revision if current else 0)
        report = {'date': plan['date'], 'meal': slot.key, 'reviewed_dishes': len(products),
                  'total_dishes': len(existing | {item.pk for item in products})}
        CatalogSyncRun.objects.create(version=plan['version'], digest=hashlib.sha256(raw).hexdigest(), report=report)
        return report
