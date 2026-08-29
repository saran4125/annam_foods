from django.contrib import admin

from apps.tenancy.adminbase import UnscopedAdmin

from .models import DeliveryZone


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(UnscopedAdmin):
    list_display = ("area_name", "pincode", "tenant", "delivery_fee", "min_order", "active")
    list_filter = ("tenant", "active")
    search_fields = ("pincode", "area_name")
