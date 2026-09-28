#!/usr/bin/env python3
"""Exercise actual HTTP boundaries and owner publishing; credentials never printed."""
import http.client, http.cookiejar, json, re, socket
from pathlib import Path
from urllib.request import build_opener, HTTPHandler, HTTPCookieProcessor, ProxyHandler, Request
from urllib.error import HTTPError
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
class LocalConnection(http.client.HTTPConnection):
    def connect(self): self.sock=socket.create_connection(('127.0.0.1',8090),20)
class LocalHandler(HTTPHandler):
    def http_open(self,request): return self.do_open(LocalConnection,request)
def client(): return build_opener(ProxyHandler({}),LocalHandler(),HTTPCookieProcessor(http.cookiejar.CookieJar()))
def fetch(opener,host,path,method='GET',data=None,headers=None):
    body=json.dumps(data).encode() if data is not None else None
    request=Request('http://'+host+':8090'+path,data=body,method=method,headers=headers or ({'Content-Type':'application/json'} if body else {}))
    try:response=opener.open(request,timeout=30)
    except HTTPError as response:
        return response.code,response.headers,response.read().decode()
    return response.status,response.headers,response.read().decode()
checks=[]
def check(condition,sentence):
    checks.append({'behaviour':sentence,'passed':bool(condition)})
    if not condition: print('FAIL:',sentence)

a=client();b=client();annam='annam.localhost';demo='demo.localhost'
status,_,html=fetch(a,annam,'/');check(status==200 and 'seer-hero' in html,'Annam homepage includes the retail artwork.')
check(len(re.findall('data-seer-slide ',html))==3,'Three independent hero slides are rendered.')
check(html.count('<source media="(max-width: 600px)"')==3,'Every slide has dedicated mobile artwork.')
status,_,unknown=fetch(a,'unregistered.localhost','/');check(status==404,'Unregistered hosts are rejected before WordPress.')
status,_,_=fetch(a,annam,'/wp-config.php');check(status in (403,404),'WordPress configuration cannot be downloaded.')
status,_,body=fetch(a,annam,'/wp-json/wc/store/v1/products?search=Halwa&per_page=100');products=json.loads(body)
check(status==200 and any(p['slug']=='tirunelveli-halwa' and p['prices']['price']=='22000' for p in products),'Halwa reconciles to the public source price of ₹220.')
p=next(p for p in products if p['slug']=='tirunelveli-halwa')
check(bool(p['images']) and 'annam.localhost' in p['images'][0]['src'],'Product imagery is served from Annam’s media library.')
status,_,body=fetch(b,demo,'/wp-json/wc/store/v1/products?search=Halwa');check(status==200 and json.loads(body)==[],'Product search cannot leak Annam items into demo.')
status,_,body=fetch(a,annam,'/products/tirunelveli-halwa/');check(status==200 and '250gm' in body and '₹' in body,'Original product URL and actual pack description are preserved.')
check('Great things are on the horizon' not in body and '<h1' in body,'Public product pages show the product rather than WooCommerce coming soon.')
status,_,body=fetch(a,annam,'/categories/sweets/');check(status==200 and 'Sweets' in body,'Original collection URLs remain usable.')
check('Great things are on the horizon' not in body and 'Badam Ghee Halwa' in body,'Public collections show photographed products.')
status,_,body=fetch(a,annam,'/shop/');check(status==200 and 'Great things are on the horizon' not in body and '2 Suttu Murukku' in body,'The public shop displays the catalog.')
check('View product' in body and 'Sold out · View product' not in body,'Unavailable products use a short secondary action that fits mobile cards.')
status,_,body=fetch(a,annam,'/?s=murukku');check(status==200 and 'Mullu Murukku' in body and 'Search Results' in body,'Store search returns products without a post_type parameter.')
status,_,body=fetch(a,annam,'/products/butter-murukku/');check(status==200 and 'alt="Butter Murukku"' in body,'Imported product imagery has a readable description.')
status,h,body=fetch(a,annam,'/wp-json/wc/store/v1/cart');token=h.get('Cart-Token');nonce=h.get('Nonce');check(bool(token),'WooCommerce issues a real anonymous cart token.')
goods=json.loads(fetch(a,annam,'/wp-json/wc/store/v1/products?slug=butter-murukku')[2])[0]
cart_headers={'Cart-Token':token,'Content-Type':'application/json'}
status,_,body=fetch(a,annam,'/wp-json/wc/store/v1/cart/add-item','POST',{'id':goods['id'],'quantity':1,'price':'0.01'},cart_headers)
cart=json.loads(body);check(status in (200,201) and cart['items'][0]['prices']['price']=='14000','Store API ignores a forged client price and uses ₹140.')
status,_,body=fetch(b,demo,'/wp-json/wc/store/v1/cart',headers={'Cart-Token':token});check(status==200 and not json.loads(body)['items'],'A cart token from Annam cannot expose Annam’s cart on demo.')
for quantity in (-1,1.5,100):
    status,_,_=fetch(a,annam,'/wp-json/wc/store/v1/cart/add-item','POST',{'id':goods['id'],'quantity':quantity},cart_headers)
    check(status>=400,'Store API rejects quantity tampering: '+str(quantity))
status,_,_=fetch(a,annam,'/wp-json/wc/store/v1/cart/extensions','POST',{'namespace':'seerkitchen','data':{'action':'context','date':'2026-09-28','slot':'lunch'}},cart_headers)
check(status>=400,'Annam cannot use the demonstration lunch window.')
for path in ['/checkout/','/?wc-ajax=checkout','/wp-json/wc/store/v1/checkout','/wp-json/wc/store/v1/batch','/wp-json/wc/v3/orders']:
    status,_,_=fetch(a,annam,path,'POST',{},cart_headers);check(status==403,'Checkout/order submission is blocked at '+path)

env=dict(line.split('=',1)for line in(ROOT/'.env').read_text().splitlines()if '=' in line and not line.startswith('#'))
owner=client()
def login(opener,host):
    fetch(opener,host,'/wp-login.php')
    request=Request('http://'+host+':8090/wp-login.php',data=urlencode({'log':'annam-owner','pwd':env['ANNAM_OWNER_PASSWORD'],'wp-submit':'Log In','testcookie':'1','redirect_to':'http://'+host+':8090/wp-admin/'}).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'})
    try: return opener.open(request).status
    except HTTPError as e:return e.code
check(login(owner,annam)==200,'Annam owner can sign in to their own administration.')
status,_,editor=fetch(owner,annam,'/wp-admin/post-new.php?post_type=page')
match=re.search(r'createNonceMiddleware\(\s*["\']([^"\']+)',editor)or re.search(r'"nonce"\s*:\s*"([^"]+)"',editor)
check(status==200 and bool(match),'Native WordPress editor is available to the owner.')
if match:
    headers={'X-WP-Nonce':match.group(1),'Content-Type':'application/json'}
    status,_,_=fetch(owner,annam,'/wp-admin/site-editor.php');check(status==200,'Owner has access to the native Site Editor.')
    status,_,media=fetch(owner,annam,'/wp-json/wp/v2/media?per_page=1&context=edit',headers=headers)
    check(status==200 and bool(json.loads(media)),'Owner can manage their site’s media.')
    image=json.loads(media)[0] if status==200 else None
    page_id=product_id=None
    try:
        content='<!-- wp:heading --><h2 class="wp-block-heading">Owner editing verification</h2><!-- /wp:heading -->'
        if image:content+='<!-- wp:image {"id":'+str(image['id'])+'} --><figure class="wp-block-image"><img src="'+image['source_url']+'" alt="Owner-selected artwork"/></figure><!-- /wp:image -->'
        status,_,body=fetch(owner,annam,'/wp-json/wp/v2/pages','POST',{'title':'Seer verification fixture','status':'draft','content':content},headers)
        check(status==201,'Owner can draft a layout with selected artwork.');page_id=json.loads(body).get('id')
        if page_id:
            status,_,body=fetch(owner,annam,f'/wp-json/wp/v2/pages/{page_id}?context=edit',headers=headers)
            check(status==200 and 'Owner-selected artwork' in json.loads(body)['content']['raw'],'Owner can retrieve and preview editable draft content.')
            content='<!-- wp:paragraph --><p>Rearranged by the owner.</p><!-- /wp:paragraph -->'+content
            status,_,body=fetch(owner,annam,f'/wp-json/wp/v2/pages/{page_id}','POST',{'content':content,'status':'publish'},headers)
            link=json.loads(body).get('link','');check(status==200 and json.loads(body).get('status')=='publish','Owner can rearrange and publish without a deployment.')
            if link:
                status,_,body=fetch(a,annam,'/'+link.split('/',3)[3]);check(status==200 and 'Rearranged by the owner' in body,'Owner-published content is visible on the storefront immediately.')
        status,_,body=fetch(owner,annam,'/wp-json/wc/v3/products','POST',{'name':'Seer owner verification fixture','type':'simple','status':'draft','regular_price':'12.50'},headers)
        product_id=json.loads(body).get('id');check(status==201 and bool(product_id),'Owner can create a product in WooCommerce.')
        if product_id:
            status,_,body=fetch(owner,annam,f'/wp-json/wc/v3/products/{product_id}','PUT',{'regular_price':'15.75','description':'Changed in owner editor.'},headers)
            check(status==200 and json.loads(body).get('regular_price')=='15.75','Owner product edits are authoritative without code changes.')
    finally:
        if page_id:fetch(owner,annam,f'/wp-json/wp/v2/pages/{page_id}','DELETE',headers=headers)
        if product_id:fetch(owner,annam,f'/wp-json/wc/v3/products/{product_id}','DELETE',headers=headers)
wrong=client();login(wrong,demo)
status,_,_=fetch(wrong,demo,'/wp-admin/')
check(status==403,'Annam credentials cannot open the demo administration.')
status,_,_=fetch(wrong,demo,'/wp-admin/upload.php');check(status==403,'Annam owner cannot manage demo media.')
status,_,_=fetch(wrong,demo,'/wp-admin/site-editor.php');check(status==403,'Annam owner cannot edit demo layouts.')
(ROOT/'reports/http-tests.json').write_text(json.dumps({'checks':checks,'passed':sum(x['passed']for x in checks),'total':len(checks)},indent=2))
print(sum(x['passed']for x in checks),'/',len(checks),'HTTP/owner checks passed.')
raise SystemExit(any(not x['passed']for x in checks))
