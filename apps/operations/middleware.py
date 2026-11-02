from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from django.utils.cache import patch_cache_control,patch_vary_headers
from .security import consume_limit,client_address


class StaffProtectionMiddleware:
    def __init__(self,get_response):self.get_response=get_response

    def __call__(self,request):
        private=request.path.startswith(('/manage/','/billing/'))
        rule=None
        if request.tenant and request.method=='POST' and request.path in ('/manage/login/','/billing/login/'):
            rule=('staff-login',getattr(settings,'STAFF_LOGIN_LIMIT',20),300)
        elif request.tenant and request.user.is_authenticated and request.path=='/billing/customer-lookup/':
            rule=('customer-lookup:'+str(request.user.pk),60,60)
        if rule:
            try:
                allowed,retry=consume_limit(rule[0],client_address(request),rule[1],rule[2])
                response=None if allowed else JsonResponse({'error':'Too many attempts. Please wait and try again.'},status=429)
                if response is not None:response['Retry-After']=str(retry)
            except DatabaseError:
                response=JsonResponse({'error':'Temporarily unavailable. Please try again shortly.'},status=503)
            if response is not None:
                patch_cache_control(response,private=True,no_store=True)
                return response
        response=self.get_response(request)
        if private:
            patch_cache_control(response,private=True,no_store=True)
            patch_vary_headers(response,['Cookie'])
            response['X-Robots-Tag']='noindex, nofollow'
        return response
