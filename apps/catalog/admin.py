from django.contrib import admin

from apps.tenancy.adminbase import UnscopedAdmin

from .models import MenuCategory, MenuItem, MenuSchedule, Slot


@admin.register(Slot)
class SlotAdmin(UnscopedAdmin):
    list_display = ("label", "key", "tenant", "order_cutoff", "active", "sort")
    list_filter = ("tenant", "active")
    ordering = ("tenant", "sort")


@admin.register(MenuCategory)
class MenuCategoryAdmin(UnscopedAdmin):
    list_display = ("name", "tenant", "sort", "active")
    list_filter = ("tenant", "active")


@admin.register(MenuItem)
class MenuItemAdmin(UnscopedAdmin):
    list_display = ("name", "tenant", "category", "price", "is_veg", "active")
    list_filter = ("tenant", "active", "is_veg", "category")
    search_fields = ("name", "description")


@admin.register(MenuSchedule)
class MenuScheduleAdmin(UnscopedAdmin):
    list_display = (
        "item", "slot", "mode", "on_date", "weekday",
        "available", "qty_limit", "qty_sold", "price_override",
    )
    list_filter = ("tenant", "mode", "slot", "available")
    autocomplete_fields = ("item",)
