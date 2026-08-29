"""Super admin. Every ModelAdmin here reads across tenants deliberately."""
from django.contrib import admin

from .context import all_tenants
from .models import Tenant, TenantConfig, TenantDomain, TenantStatus, TenantUser


class UnscopedAdmin(admin.ModelAdmin):
    """Platform staff work across every kitchen, so opt out of scoping here."""

    def get_queryset(self, request):
        with all_tenants():
            return super().get_queryset(request)


class TenantDomainInline(admin.TabularInline):
    model = TenantDomain
    extra = 1


class TenantConfigInline(admin.StackedInline):
    model = TenantConfig
    can_delete = False


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "primary_domain", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "primary_domain")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantConfigInline, TenantDomainInline]
    actions = ["mark_active", "mark_past_due", "mark_restricted", "mark_suspended"]

    @admin.action(description="Restore to Active")
    def mark_active(self, request, queryset):
        queryset.update(status=TenantStatus.ACTIVE)

    @admin.action(description="Mark past due (owner sees a banner)")
    def mark_past_due(self, request, queryset):
        queryset.update(status=TenantStatus.PAST_DUE)

    @admin.action(description="Restrict (backend read-only, storefront still sells)")
    def mark_restricted(self, request, queryset):
        queryset.update(status=TenantStatus.RESTRICTED)

    @admin.action(description="Suspend (ordering off, owner keeps access)")
    def mark_suspended(self, request, queryset):
        queryset.update(status=TenantStatus.SUSPENDED)


@admin.register(TenantUser)
class TenantUserAdmin(UnscopedAdmin):
    list_display = ("user", "tenant", "role", "created_at")
    list_filter = ("role", "tenant")
    search_fields = ("user__username", "user__email")
