"""Read-only HTTP boundary checks for the local isolated PHP preview."""
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE='http://127.0.0.1:8091'
def status(path,method='GET',headers=None,data=None):
    try:
        with urlopen(Request(BASE+path,method=method,headers=headers or {},data=data),timeout=10) as response:
            return response.status,response.read()
    except HTTPError as error:
        return error.code,error.read()

for path in ['/.env','/php-app/.env','/src/bootstrap.php','/storage/logs/php.log','/bin/cron.php','/media/website/1/private.jpg','/platform/assets/another-store/00000000-0000-0000-0000-000000000000/']:
    assert status(path)[0]==404,path
assert status('/cart/clear/','POST',data=b'')[0]==403
assert status('/','GET',headers={'Host':'untrusted.example'})[0]==404
assert status('/healthz')[0]==200
assert status('/assets/receipt.css')[0]==200
assert status('/webhooks/whatsapp/n8n/','POST',data=b'{}')[0]==403
assert status('/platform/webhooks/annam/razorpay/test/','POST',data=b'{}')[0] in (403,404)
print('PASS private paths, unknown hosts, CSRF and unauthenticated provider callback checks')
