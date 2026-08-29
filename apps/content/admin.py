from django.contrib import admin

from apps.tenancy.adminbase import UnscopedAdmin

from .models import Banner, Page


@admin.register(Page)
class PageAdmin(UnscopedAdmin):
    list_display = ("title", "slug", "tenant", "published", "show_in_nav", "updated_at")
    list_filter = ("tenant", "published", "show_in_nav")
    search_fields = ("title", "body_md")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Banner)
class BannerAdmin(UnscopedAdmin):
    list_display = ("title", "tenant", "active", "sort")
    list_filter = ("tenant", "active")
