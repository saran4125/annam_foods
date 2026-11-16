from datetime import date

import pytest

from apps.catalog.meal_categories import normalize_meal_categories
from apps.catalog.models import MenuCategory, MenuDay, MenuItem, MenuSchedule, Slot
from apps.owner.forms import DishForm
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Tenant


@pytest.mark.django_db
def test_weekday_categories_consolidate_without_changing_dishes_or_daily_menus():
    store = Tenant.objects.create(slug='annam', name='Annam')
    with tenant_context(store):
        breakfast = MenuCategory.objects.create(name='Breakfast', slug='breakfast')
        tuesday = MenuCategory.objects.create(name='Tuesday Breakfast', slug='tuesday-breakfast')
        friday = MenuCategory.objects.create(name='Friday Breakfast', slug='friday-breakfast')
        dinner = MenuCategory.objects.create(name='Monday Dinner', slug='monday-dinner')
        items = [MenuItem.objects.create(name='Idly', price='110', category=category,
                                        image='menu/original.jpg', in_stock=False)
                 for category in (tuesday, friday, dinner)]
        slot = Slot.objects.create(key='breakfast', label='Breakfast', order_cutoff='09:00')
        MenuDay.objects.create(slot=slot, on_date=date(2026, 11, 16))
        MenuSchedule.objects.create(item=items[0], slot=slot, mode='date',
                                    on_date=date(2026, 11, 17), qty_sold=2, qty_limit=5)
        before = list(MenuSchedule.objects.values())
        days = list(MenuDay.objects.values())
        assert normalize_meal_categories(store)['moved_dishes'] == 3
        for item in items:
            item.refresh_from_db()
            assert item.category.name in ('Breakfast', 'Dinner')
            assert str(item.price) == '110.00'
            assert item.image.name == 'menu/original.jpg' and not item.in_stock
        assert MenuItem.objects.filter(category=breakfast).count() == 2
        assert list(MenuSchedule.objects.values()) == before
        assert list(MenuDay.objects.values()) == days
        assert not MenuCategory.objects.get(pk=tuesday.pk).active
        assert not DishForm().fields['category'].queryset.filter(pk=tuesday.pk).exists()
        assert normalize_meal_categories(store) == {'moved_dishes': 0, 'archived_categories': 0}


@pytest.mark.django_db
def test_shop_festival_categories_and_other_tenants_are_preserved():
    store = Tenant.objects.create(slug='annam', name='Annam')
    other = Tenant.objects.create(slug='other', name='Other')
    with tenant_context(other):
        foreign = MenuCategory.objects.create(name='Tuesday Breakfast', slug='tuesday-breakfast')
        foreign_item = MenuItem.objects.create(name='Idly', price=20, category=foreign)
    with tenant_context(store):
        mixed = MenuCategory.objects.create(name='Tuesday Breakfast', slug='tuesday-breakfast')
        festival = MenuCategory.objects.create(name='Festival Lunch', slug='festival-lunch')
        goods = MenuItem.objects.create(name='Podi', price=50, fulfilment='courier', category=mixed)
        festive = MenuItem.objects.create(name='Special meal', price=150, category=festival)
        MenuItem.objects.create(name='Idly', price=20, category=mixed)
        normalize_meal_categories(store)
        goods.refresh_from_db(); festive.refresh_from_db(); mixed.refresh_from_db()
        assert goods.category_id == mixed.pk and mixed.active
        assert festive.category_id == festival.pk
    foreign_item.refresh_from_db(); foreign.refresh_from_db()
    assert foreign_item.category_id == foreign.pk and foreign.active
