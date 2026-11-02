"""Shared database limits work across web workers; no raw IPs or login names are retained."""
import hashlib
import ipaddress
from datetime import datetime,timedelta,timezone as utc
from django.conf import settings
from django.db.models import F
from django.utils import timezone
from django.views.debug import SafeExceptionReporterFilter
from .models import RateLimitBucket


def client_address(request):
    hops=getattr(settings,'TRUSTED_PROXY_HOPS',0)
    forwarded=request.META.get('HTTP_X_FORWARDED_FOR','').split(',')
    value=forwarded[-hops].strip() if hops and len(forwarded)>=hops else request.META.get('REMOTE_ADDR','')
    try:return str(ipaddress.ip_address(value))
    except ValueError:return 'unknown'


def consume_limit(scope,identity,limit,seconds):
    now=timezone.now();start=int(now.timestamp())//seconds*seconds
    begins=datetime.fromtimestamp(start,tz=utc.utc);ends=begins+timedelta(seconds=seconds)
    key=hashlib.sha256((scope+'\0'+identity).encode()).hexdigest()
    bucket,_=RateLimitBucket.objects.get_or_create(key=key,window_start=begins,defaults={'expires_at':ends})
    accepted=RateLimitBucket.objects.filter(pk=bucket.pk,attempts__lt=limit).update(attempts=F('attempts')+1)
    return bool(accepted),max(1,int((ends-now).total_seconds())+1)


class PrivateExceptionReporterFilter(SafeExceptionReporterFilter):
    def get_post_parameters(self,request):return {'request_body':'[redacted]'}
    def get_traceback_frame_variables(self,request,tb_frame):return [('frame locals','[redacted]')]
    def get_safe_request_meta(self,request):
        data=super().get_safe_request_meta(request)
        for key in ('QUERY_STRING','RAW_URI','REQUEST_URI','HTTP_COOKIE','HTTP_AUTHORIZATION'):
            if key in data:data[key]='[redacted]'
        return data


from django.views.debug import ExceptionReporter
import logging
import traceback


class PrivateExceptionReporter(ExceptionReporter):
    def get_traceback_data(self):
        data=super().get_traceback_data()
        for name in ('request_GET_items','request_FILES_items','request_COOKIES_items'):
            data[name]=[]
        if self.request is not None:
            data['request_insecure_uri']=self.request.build_absolute_uri(self.request.path)
        data['exception_value']='Details redacted; inspect exception type and source frames.'
        return data


class PrivateLogFormatter(logging.Formatter):
    def formatException(self,exc_info):
        return ''.join(traceback.format_tb(exc_info[2]))+exc_info[0].__name__+': exception details redacted'
