import pytest
from django.test import RequestFactory,override_settings
from apps.owner.tests.test_owner import kitchens,owner,signed_in,catalog,HOST,OTHER
from apps.tenancy.context import tenant_context
from apps.operations.models import RateLimitBucket
from apps.operations.security import client_address,consume_limit,PrivateExceptionReporterFilter


def test_staff_login_limits_are_shared_between_billing_and_management(client,kitchens,settings):
    settings.STAFF_LOGIN_LIMIT=2
    credentials={'username':'wrong-user','password':'wrong-password'}
    assert client.post('/manage/login/',credentials,HTTP_HOST=HOST).status_code==200
    assert client.post('/billing/login/',credentials,HTTP_HOST=HOST).status_code==200
    blocked=client.post('/manage/login/',credentials,HTTP_HOST=HOST)
    assert blocked.status_code==429 and int(blocked['Retry-After'])>0
    assert 'no-store' in blocked['Cache-Control']
    assert client.post('/manage/login/',credentials,HTTP_HOST=OTHER).status_code==200
    with tenant_context(kitchens[0]):
        bucket=RateLimitBucket.objects.get();assert bucket.attempts==2
        assert '127.0.0.1' not in bucket.key and len(bucket.key)==64


def test_forwarded_ip_is_ignored_without_explicit_proxy_trust(settings):
    request=RequestFactory().get('/',REMOTE_ADDR='192.0.2.1',HTTP_X_FORWARDED_FOR='198.51.100.7, 203.0.113.8')
    settings.TRUSTED_PROXY_HOPS=0;assert client_address(request)=='192.0.2.1'
    settings.TRUSTED_PROXY_HOPS=1;assert client_address(request)=='203.0.113.8'


def test_staff_customer_and_bill_pages_never_allow_shared_caching(signed_in,catalog):
    for path in ['/manage/orders/','/manage/categories/','/billing/','/billing/new/']:
        response=signed_in.get(path,HTTP_HOST=HOST)
        assert response.status_code==200 and 'private' in response['Cache-Control'] and 'no-store' in response['Cache-Control']
        assert 'Cookie' in response['Vary'] and response['X-Robots-Tag']=='noindex, nofollow'


def test_error_reporting_omits_customer_body_tokens_and_frame_locals():
    request=RequestFactory().post('/billing/new/',{'phone':'private-number','address':'private-address'})
    request.META.update(HTTP_AUTHORIZATION='Bearer private-token',QUERY_STRING='phone=private-number')
    reporter=PrivateExceptionReporterFilter()
    assert 'private' not in str(reporter.get_post_parameters(request))
    meta=reporter.get_safe_request_meta(request)
    assert meta['QUERY_STRING']=='[redacted]' and meta['HTTP_AUTHORIZATION']=='[redacted]'
    assert reporter.get_traceback_frame_variables(request,None)==[('frame locals','[redacted]')]


def test_public_media_cannot_serve_private_symlinks_or_non_images(client,kitchens,settings,tmp_path):
    settings.MEDIA_ROOT=tmp_path/'public';settings.MEDIA_ROOT.mkdir()
    private=tmp_path/'private.jpg';private.write_bytes(b'private content')
    (settings.MEDIA_ROOT/'leak.jpg').symlink_to(private)
    (settings.MEDIA_ROOT/'page.html').write_text('<script>private content</script>')
    assert client.get('/media/leak.jpg',HTTP_HOST=HOST).status_code==404
    assert client.get('/media/page.html',HTTP_HOST=HOST).status_code==404
    (settings.MEDIA_ROOT/'website').mkdir()
    protected=settings.MEDIA_ROOT/'website'/'private.jpg';protected.write_bytes(b'private library image')
    (settings.MEDIA_ROOT/'library-alias.jpg').symlink_to(protected)
    assert client.get('/media/library-alias.jpg',HTTP_HOST=HOST).status_code==404


@pytest.mark.django_db(transaction=True)
def test_concurrent_web_workers_share_a_single_login_allowance(kitchens):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections,connections
    gate=Barrier(2)
    def attempt(_):
        close_old_connections()
        try:
            with tenant_context(kitchens[0]):
                gate.wait(timeout=10)
                return consume_limit('parallel-login','test-address',1,300)[0]
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(attempt,range(2)))
    assert sorted(results)==[False,True]


def test_rendered_error_reports_and_logs_do_not_include_customer_query_or_exception_details(settings):
    import sys
    from apps.operations.security import PrivateExceptionReporter,PrivateLogFormatter
    settings.DEFAULT_EXCEPTION_REPORTER_FILTER='apps.operations.security.PrivateExceptionReporterFilter'
    import secrets
    sensitive=[secrets.token_hex(20) for _ in range(3)]
    request=RequestFactory().post('/billing/new/?phone='+sensitive[0],{'address':sensitive[1]})
    try:raise ValueError(sensitive[2])
    except ValueError:exc_info=sys.exc_info()
    report=PrivateExceptionReporter(request,*exc_info).get_traceback_text()
    assert all(value not in report for value in sensitive)
    logged=PrivateLogFormatter().formatException(exc_info)
    assert sensitive[2] not in logged and 'ValueError' in logged
