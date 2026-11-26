import os
import re
from django.conf import settings
from django.db import connection, DatabaseError
from django.http import JsonResponse
from django.urls import include, path, re_path
from apps.content.media import public_media
from apps.operations.health import readyz


def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    result={'status':'ok'}
    revision=os.environ.get('RENDER_GIT_COMMIT','')
    if re.fullmatch(r'[a-f0-9]{40}',revision):result['revision']=revision
    return JsonResponse(result)


urlpatterns = [
    path("platform/", include("apps.platform_portal.urls")),
    path("readyz", readyz, name="readyz"),
    path("healthz", healthz, name="healthz"),
    path("webhooks/whatsapp/", include("apps.messaging.webhook_urls")),
    path("billing/", include("apps.billing.urls")),
    path("manage/", include("apps.owner.urls")),
    path("", include("apps.storefront.urls")),
]

urlpatterns += [re_path(r"^media/(?P<path>.*)$", public_media, name="public_media")]
