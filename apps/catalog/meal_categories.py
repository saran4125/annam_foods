"""Consolidate weekday-labelled meal shelves without changing availability."""
import re

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant
from .models import MenuCategory, MenuItem


WEEKDAY_MEAL = re.compile(
    r'^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*[-–:]?\s*'
    r'(Breakfast|Lunch|Dinner|Snacks)$', re.IGNORECASE,
)


@transaction.atomic
def normalize_meal_categories(tenant):
    # Serialize against other catalog maintenance for this store.
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    report = {'moved_dishes': 0, 'archived_categories': 0}
    with tenant_context(tenant):
        for source in list(MenuCategory.objects.all()):
            match = WEEKDAY_MEAL.fullmatch(source.name.strip())
            if not match:
                continue
            dishes = MenuItem.objects.filter(category=source, fulfilment='scheduled')
            if dishes.exists():
                name = match.group(1).title()
                targets = list(MenuCategory.objects.filter(name__iexact=name))
                if len(targets) > 1:
                    raise ValidationError(f'Multiple {name} categories need staff review.')
                target = targets[0] if targets else None
                if target is None:
                    if MenuCategory.objects.filter(slug=name.lower()).exists():
                        raise ValidationError(f'The {name.lower()} category address is already in use.')
                    target = MenuCategory.objects.create(
                        name=name, slug=name.lower(), sort=source.sort,
                        image=source.image, description=source.description,
                    )
                report['moved_dishes'] += dishes.update(category=target)
            # Keep old category URLs and metadata, and never hide a shop shelf
            # or parent still in use. No products or schedule rows are deleted.
            if source.active and not MenuItem.objects.filter(category=source).exists() and not source.children.exists():
                source.active = False
                source.save(update_fields=['active'])
                report['archived_categories'] += 1
    return report
