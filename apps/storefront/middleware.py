"""Persist guest receipt access independently of staff authentication sessions."""
from django.conf import settings


class GuestOrderCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        value = getattr(request, '_guest_order_browser', None)
        if value and request.tenant and response.status_code < 500:
            response.set_signed_cookie('guest_order_' + str(request.tenant.pk), value,
                                       salt='guest-order-browser', max_age=30 * 86400,
                                       secure=settings.SESSION_COOKIE_SECURE,
                                       httponly=True, samesite='Lax')
            response['Cache-Control'] = 'private, no-store'
        return response
