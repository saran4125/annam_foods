from django.contrib import admin

from apps.tenancy.adminbase import UnscopedAdmin

from .models import Address, Customer, Order, OrderEvent


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "actor", "note", "at")
    can_delete = False


@admin.register(Customer)
class CustomerAdmin(UnscopedAdmin):
    list_display = ("phone", "name", "tenant", "source", "last_seen")
    list_filter = ("tenant", "source")
    search_fields = ("phone", "name", "email")


@admin.register(Address)
class AddressAdmin(UnscopedAdmin):
    list_display = ("line1", "pincode", "customer", "tenant", "is_default")
    list_filter = ("tenant",)
    search_fields = ("pincode", "line1")


@admin.register(Order)
class OrderAdmin(UnscopedAdmin):
    list_display = ("order_no", "tenant", "channel", "status", "payment_status",
                    "delivery_date", "slot", "total", "placed_at")
    list_filter = ("tenant", "channel", "status", "payment_status", "delivery_date")
    search_fields = ("order_no", "customer__phone")
    readonly_fields = ("items", "address", "subtotal", "delivery_fee", "total", "placed_at")
    inlines = [OrderEventInline]
