"""Shared admin behaviour for tenant-owned models."""
from django.contrib import admin

from .context import all_tenants


class UnscopedAdmin(admin.ModelAdmin):
    """SEER staff work across every kitchen, so opt out of tenant scoping.

    Deliberately explicit: the default manager raises without a tenant, and
    this is the one place that's meant to see everything.
    """

    def get_queryset(self, request):
        with all_tenants():
            return super().get_queryset(request)

    def get_object(self, request, object_id, from_field=None):
        with all_tenants():
            return super().get_object(request, object_id, from_field)

    def save_model(self, request, obj, form, change):
        with all_tenants():
            super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        with all_tenants():
            return super().formfield_for_foreignkey(db_field, request, **kwargs)
