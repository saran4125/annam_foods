import os
import tempfile
from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.db import connection,DatabaseError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from .models import WorkerPulse


def pulse_worker(name='inbox'):
    from apps.tenancy.models import Tenant
    from apps.tenancy.context import tenant_context
    from apps.tenancy.deployment import deployment_rows
    for tenant in deployment_rows(Tenant.objects.all(),'slug'):
        with tenant_context(tenant):
            WorkerPulse.objects.update_or_create(name=name,defaults={'updated_at':timezone.now()})


def storage_writable():
    for root in (settings.MEDIA_ROOT,getattr(settings,'PRIVATE_BILLS_ROOT',settings.BASE_DIR/'private-bills')):
        path=Path(root);path.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=path) as probe:
            probe.write(b'health');probe.flush()
    return True


@never_cache
def readyz(request):
    try:
        with connection.cursor() as cursor:cursor.execute('SELECT 1')
        if getattr(settings,'READINESS_CHECK_STORAGE',False):storage_writable()
        if getattr(settings,'REQUIRE_WORKER_HEARTBEAT',False):
            from apps.tenancy.deployment import deployment_rows
            threshold=timezone.now()-timedelta(seconds=90)
            query=deployment_rows(WorkerPulse.all_tenants.filter(name='inbox',updated_at__gte=threshold))
            if not query.exists():return JsonResponse({'status':'unavailable'},status=503)
    except (DatabaseError,OSError):
        return JsonResponse({'status':'unavailable'},status=503)
    return JsonResponse({'status':'ok'})
