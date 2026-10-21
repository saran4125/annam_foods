"""Small fixed-host Razorpay REST adapter; errors never include response bodies or credentials."""
import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler


class PaymentError(Exception):
    def __init__(self, message='Razorpay is temporarily unavailable. Please check the payment status before retrying.', *, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Razorpay:
    def __init__(self, connection):
        self.key_id = connection.key_id
        self.secret = connection.key_secret
        if not self.key_id or not self.secret:
            raise PaymentError('Razorpay is not configured for this payment.')

    def call(self, method, path, payload=None, headers=None):
        auth = base64.b64encode(f'{self.key_id}:{self.secret}'.encode()).decode()
        req = Request('https://api.razorpay.com/v1/' + path, method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json', **(headers or {})})
        try:
            with build_opener(NoRedirect()).open(req, timeout=8) as response:
                result = json.loads(response.read(1024 * 1024))
            if not isinstance(result, dict):
                raise ValueError
            return result
        except HTTPError as exc:
            raise PaymentError(uncertain=exc.code >= 500 or exc.code == 408) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise PaymentError(uncertain=method == 'POST') from None

    @staticmethod
    def identifier(value, prefix):
        if not isinstance(value, str) or not re.fullmatch(prefix + r'_[A-Za-z0-9]{1,70}', value):
            raise PaymentError('Invalid Razorpay reference.')
        return value

    def create_order(self, intent):
        return self.call('POST', 'orders', {'amount': intent.amount, 'currency': intent.currency,
            'receipt': intent.receipt, 'notes': {'seer_payment': intent.pk.hex}})

    def find_order(self, intent):
        result = self.call('GET', 'orders?' + urlencode({'receipt': intent.receipt, 'count': 100}))
        return next((item for item in result.get('items', []) if item.get('receipt') == intent.receipt), None)

    def payment(self, payment_id):
        return self.call('GET', 'payments/' + self.identifier(payment_id, 'pay'))

    def order_payments(self, intent):
        return self.call('GET', 'orders/' + self.identifier(intent.provider_order_id, 'order') + '/payments').get('items', [])

    def refund(self, intent, refund):
        return self.call('POST', 'payments/' + self.identifier(intent.payment_id, 'pay') + '/refund',
            {'amount': refund.amount, 'notes': {'seer_refund': refund.pk.hex}},
            {'X-Refund-Idempotency': refund.pk.hex})

    def refunds(self, intent):
        return self.call('GET', 'payments/' + self.identifier(intent.payment_id, 'pay') + '/refunds?count=100').get('items', [])

    def refund_status(self, provider_id):
        return self.call('GET', 'refunds/' + self.identifier(provider_id, 'rfnd'))
