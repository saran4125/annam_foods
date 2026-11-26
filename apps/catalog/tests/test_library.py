from datetime import timedelta
import pytest
from django.utils import timezone
from apps.owner.tests.test_owner import kitchens, owner, signed_in, HOST
from apps.catalog.library import ensure_defaults, for_meal, meal_keys, category_items
from apps.catalog.models import MenuCategory, MenuItem, MenuSchedule, Slot
from apps.owner.forms import DishForm
from apps.tenancy.context import tenant_context


def test_four_defaults_and_shared_meal_membership_do_not_publish_daily_menus(kitchens):
    with tenant_context(kitchens[0]):
        ensure_defaults();ensure_defaults()
        assert set(MenuCategory.objects.values_list('slug',flat=True))=={'breakfast','lunch','dinner','shop'}
        assert set(Slot.objects.values_list('key',flat=True))=={'breakfast','lunch','dinner'}
        form=DishForm({'name':'Shared meal','price':'100','category':'','fulfilment':'scheduled','sort':0,'in_stock':'on','active':'on','membership_editor':'1','meals':['breakfast','lunch','dinner']})
        assert form.is_valid(),form.errors
        item=form.save()
        assert meal_keys(item)==['breakfast','lunch','dinner'] and not MenuSchedule.objects.filter(item=item).exists()
        for key in ('breakfast','lunch','dinner'):
            assert category_items(MenuCategory.objects.get(slug=key)).filter(pk=item.pk).exists()
        assert not category_items(MenuCategory.objects.get(slug='shop')).filter(pk=item.pk).exists()
