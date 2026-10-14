"""Super admin. Every ModelAdmin here reads across tenants deliberately."""
from django.contrib import admin

from .adminbase import UnscopedAdmin
from .forms import TenantSecretsForm
from .models import (
    Tenant,
    TenantConfig,
    BillingProfile,
    TenantDomain,
    TenantSecrets,
    TenantStatus,
    TenantUser,
)


class TenantDomainInline(admin.TabularInline):
    model = TenantDomain
    extra = 1


class TenantConfigInline(admin.StackedInline):
    model = TenantConfig
    can_delete = False
    extra = 0


class BillingProfileInline(admin.StackedInline):
    model = BillingProfile
    can_delete = False
    extra = 0


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "primary_domain", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "primary_domain")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [TenantConfigInline, BillingProfileInline, TenantDomainInline]
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


@admin.register(TenantSecrets)
class TenantSecretsAdmin(admin.ModelAdmin):
    """Credentials are write-only here. See TenantSecretsForm for why."""

    form = TenantSecretsForm
    list_display = ("tenant", "wa_provider", "whatsapp_ready", "razorpay_ready")
    list_filter = ("wa_provider", "razorpay_live_mode")

    @admin.display(boolean=True, description="WhatsApp ready")
    def whatsapp_ready(self, obj):
        return obj.whatsapp_is_configured

    @admin.display(boolean=True, description="Razorpay ready")
    def razorpay_ready(self, obj):
        return obj.razorpay_is_configured
