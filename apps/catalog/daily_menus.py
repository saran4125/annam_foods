"""Explicit date menus. Never infer recurrence from an imported category name."""
from django.core.exceptions import ValidationError
from django.db import transaction
from apps.tenancy.models import TenantConfig
from apps.tenancy.context import get_current_tenant
from .models import MenuDay, MenuItem, MenuSchedule, ScheduleMode, Slot
from .services import models_q_date, models_q_weekday


def _lock_store(slot):
    tenant = get_current_tenant()
    if tenant is None or slot.tenant_id != tenant.pk:
        raise ValidationError('This meal does not belong to this store.')
    TenantConfig.objects.select_for_update().get(tenant=tenant)


def _materialize(slot, on_date):
    """Freeze the effective menu first, so other existing dishes are not lost."""
    plan = MenuDay.objects.filter(slot=slot, on_date=on_date).first()
    if plan:
        return plan
    weekly, dated = {}, {}
    rows = MenuSchedule.objects.filter(slot=slot, item__fulfilment='scheduled').filter(
        models_q_date(on_date) | models_q_weekday(on_date.weekday()))
    for row in rows:
        (dated if row.mode == ScheduleMode.DATE else weekly)[row.item_id] = row
    for item_id, source in {**weekly, **dated}.items():
        if item_id not in dated:
            MenuSchedule.objects.create(item_id=item_id, slot=slot, mode=ScheduleMode.DATE, on_date=on_date,
                available=source.available, qty_limit=source.qty_limit, qty_sold=source.qty_sold,
                price_override=source.price_override)
    return MenuDay.objects.create(slot=slot, on_date=on_date)


def _check_revision(slot, on_date, revision):
    current = MenuDay.objects.filter(slot=slot, on_date=on_date).first()
    if revision is not None and revision != (current.revision if current else 0):
        raise ValidationError('This menu changed in another session. Reload before saving.')


@transaction.atomic
def save_daily_menu(*, slot, on_date, item_ids, revision):
    _lock_store(slot)
    _check_revision(slot, on_date, revision)
    ids = set(item_ids)
    allowed = set(MenuItem.objects.filter(pk__in=ids, fulfilment='scheduled').values_list('pk', flat=True))
    if ids != allowed:
        raise ValidationError('Choose dishes from this store only.')
    plan = _materialize(slot, on_date)
    dated = MenuSchedule.objects.filter(slot=slot, mode=ScheduleMode.DATE, on_date=on_date)
    dated.exclude(item_id__in=ids).update(available=False)
    for pk in ids:
        MenuSchedule.objects.update_or_create(item_id=pk, slot=slot, mode=ScheduleMode.DATE, on_date=on_date,
                                              defaults={'available': True})
    plan.revision += 1
    plan.save(update_fields=['revision', 'updated_at'])
    return plan


@transaction.atomic
def set_daily_availability(*, slot, on_date, item, available, revision=None):
    _lock_store(slot)
    if item.tenant_id != slot.tenant_id or item.fulfilment != 'scheduled':
        raise ValidationError('Choose a meal dish from this store.')
    _check_revision(slot, on_date, revision)
    plan = _materialize(slot, on_date)
    MenuSchedule.objects.update_or_create(item=item, slot=slot, mode=ScheduleMode.DATE, on_date=on_date,
                                          defaults={'available': available})
    plan.revision += 1
    plan.save(update_fields=['revision', 'updated_at'])
    return plan
