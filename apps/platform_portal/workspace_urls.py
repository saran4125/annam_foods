"""Reuse existing tools with workspace-scoped URL reversals, not copied views."""
from functools import lru_cache
from django.urls import include, path


@lru_cache(maxsize=128)
def workspace_urlconf(slug):
    root = f"platform/workspaces/{slug}/"
    return (
        path(root + "manage/", include("apps.owner.urls", namespace="owner")),
        path(root + "billing/", include("apps.billing.urls", namespace="billing")),
        path(root + "preview/", include("apps.storefront.urls", namespace="storefront")),
        path(f"platform/webhooks/{slug}/whatsapp/", include("apps.messaging.webhook_urls", namespace="whatsapp_webhooks")),
        path("", include("config.urls")),
    )
