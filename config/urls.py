from django.conf import settings
from django.contrib import admin
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.urls import include, path, re_path
from apps.content.media import public_media
from apps.platform_portal.views import root
from apps.platform_portal.domain_views import probe


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path(".well-known/seerkitchen-domain", probe, name="domain_probe"),
    path("platform/", include("apps.platform_portal.urls")),
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("webhooks/whatsapp/", include("apps.messaging.webhook_urls")),
    path("billing/", include("apps.billing.urls")),
    path("manage/", include("apps.owner.urls")),
    path("", root),
    path("", include("apps.storefront.urls")),
]

urlpatterns += [re_path(r"^media/(?P<path>.*)$", public_media, name="public_media")]
