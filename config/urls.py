from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.urls import include, path
from apps.platform_portal.views import root


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("platform/", include("apps.platform_portal.urls")),
    path("healthz", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("webhooks/whatsapp/", include("apps.messaging.webhook_urls")),
    path("billing/", include("apps.billing.urls")),
    path("manage/", include("apps.owner.urls")),
    path("", root),
    path("", include("apps.storefront.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    from django.urls import re_path
    from django.views.static import serve

    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
