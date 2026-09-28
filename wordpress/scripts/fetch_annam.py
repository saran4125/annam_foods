#!/usr/bin/env python3
"""Read-only public catalog export. TLS remains verified; no login or cart calls.

Only explicitly allowlisted public fields are persisted. The source includes
serialized JavaScript Sets/undefined; normalise those without evaluating code.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

BASE = 'https://www.annamfood.in'
ROOT = Path(__file__).resolve().parents[1]
PUBLIC_API = 'https://annams.commmerce.com/store/api'

def fetch_api(endpoint, payload):
    # These POST endpoints are public read operations used by the storefront.
    # Never call any login, cart, checkout, customer or order endpoint.
    if endpoint not in {'/category/getCategories/', '/products/productList/', '/products/productDetails/'}:
        raise ValueError('Not a public catalog read endpoint.')
    data = json.dumps({**payload, 'deviceIp':'127.0.0.1'}).encode()
    ca=Path('/etc/ssl/cert.pem')
    context=ssl.create_default_context(cafile=str(ca) if ca.exists() else None)
    for attempt in range(3):
        try:
            req=Request(PUBLIC_API+endpoint,data=data,headers={'Content-Type':'application/json','User-Agent':'SeerKitchen-Catalog-Migration/1.0'})
            with urlopen(req,timeout=35,context=context) as response:
                if urlsplit(response.url).hostname != 'annams.commmerce.com': raise ValueError('Unexpected catalog API redirect.')
                result=json.load(response)
                if result.get('status') not in {'success',None}: raise ValueError('Source catalog did not return success.')
                return result
        except Exception:
            if attempt==2: raise
            time.sleep(attempt+1)

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'): self.links.append(attrs['href'])

def state_from_html(html):
    marker = 'window.INITIAL_STATE = '
    if marker not in html: raise ValueError('Source did not expose catalog state; use an owner export.')
    literal = html.split(marker, 1)[1].split('</script>', 1)[0].strip().rstrip(';')
    literal = re.sub(r'new Set\((\[[^)]*\])\)', r'\1', literal)
    literal = re.sub(r'("(?:\\.|[^"\\])*"|\bundefined\b)', lambda m: 'null' if m.group(0) == 'undefined' else m.group(0), literal)
    return json.loads(literal)

def fetch(url, *, binary=False):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.annamfood.in', 'cdn.commmerce.com'}:
        raise ValueError('Source URL is outside the approved HTTPS hosts.')
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'SeerKitchen-Catalog-Migration/1.0'})
            ca = Path('/etc/ssl/cert.pem')
            context = ssl.create_default_context(cafile=str(ca) if ca.exists() else None)
            with urlopen(request, timeout=35, context=context) as response:
                final = urlsplit(response.url)
                if final.hostname not in {'www.annamfood.in', 'cdn.commmerce.com'} or final.scheme != 'https':
                    raise ValueError('Unexpected source redirect.')
                data = response.read(12 * 1024 * 1024 + 1)
                if len(data) > 12 * 1024 * 1024: raise ValueError('Source file exceeds 12 MB.')
                return data if binary else data.decode('utf-8')
        except Exception:
            if attempt == 2: raise
            time.sleep(attempt + 1)

def canonical(path):
    parsed = urlsplit(urljoin(BASE, path))
    return BASE + parsed.path + (('?' + parsed.query) if parsed.query else '')

def amount(value):
    try:
        money = Decimal(str(value))
        if not money.is_finite() or money < 0: return None
        return str(money.quantize(Decimal('.01')))
    except InvalidOperation: return None

def images(info):
    values = [x.get('full') for x in info.get('images', []) if isinstance(x, dict)]
    return list(dict.fromkeys(x for x in values if x and urlsplit(x).hostname == 'cdn.commmerce.com'))

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'data/catalog.json')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    report = {'source': BASE, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'failures': [], 'categories': [], 'products': [], 'pages': [], 'campaigns': []}
    homepage = fetch(BASE+'/')
    state = state_from_html(homepage)
    store = state['StoreData']['storeData']
    report['brand'] = {'name': store.get('store_name', 'Annam Foods'), 'logo': store.get('logo'), 'favicon': store.get('favicon')}
    queue = {BASE+'/categories'}
    seen = set(); categories = {}; product_categories = {}; product_slugs = set()
    while queue:
        batch = sorted(queue-seen); queue.clear()
        if not batch: break
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(fetch, url): url for url in batch}
            for future in as_completed(futures):
                url = futures[future]; seen.add(url)
                try:
                    html = future.result(); source = state_from_html(html)
                    data = source.get('categoryReducer', {})
                    current = data.get('categoryData') or {}
                    for row in walk(data):
                        if row.get('slug') and row.get('name') and ('parentId' in row or ('children' in row and 'sellingPrice' not in row)):
                            slug = row['slug']
                            categories[slug] = {'source_id': str(row.get('id',slug)), 'slug':slug, 'name':row['name'], 'parent_id':str(row.get('parentId','0')), 'image':row.get('image',''), 'description':row.get('description',''), 'source_url':BASE+'/categories/'+slug}
                            target = BASE+'/categories/'+slug
                            if target not in seen: queue.add(target)
                    links = Links(); links.feed(html)
                    for link in links.links:
                        path = urlsplit(link).path
                        if path.startswith('/categories/'):
                            target = canonical(link)
                            if target not in seen: queue.add(target)
                        if path.startswith('/products/'):
                            slug = path.removeprefix('/products/').strip('/')
                            product_slugs.add(slug)
                            if current.get('slug'): product_categories.setdefault(slug,set()).add(current['slug'])
                    for product in data.get('categoryListProduct', []):
                        if product.get('slug'):
                            product_slugs.add(product['slug'])
                            if current.get('slug'): product_categories.setdefault(product['slug'],set()).add(current['slug'])
                except Exception as exc: report['failures'].append({'url':url,'error':str(exc)})
        if len(seen)+len(queue)>500: raise ValueError('Category crawl exceeded the safety bound.')
    report['categories'] = sorted(categories.values(), key=lambda x:x['slug'])
    # The source sometimes serves an empty hydrated state. Read its documented-in-
    # bundle public catalog endpoints to reconcile categories and every page.
    roots=fetch_api('/category/getCategories/', {'dummy':False}).get('categories',[])
    known={row['slug']:row for row in walk(roots) if row.get('slug') and row.get('name')}
    def read_category(slug):
        detail=fetch_api('/category/getCategories/',{'category':slug,'dummy':False})
        current=detail.get('category') or known[slug]
        products=[]; page=1
        while page<=50:
            listing=fetch_api('/products/productList/',{'page':page,'limit':100,'category':slug,'sort':'featured','filter':None})
            chunk=listing.get('products',[])
            products.extend(chunk)
            total=int(listing.get('total_products') or 0)
            if not chunk or len(products)>=total: break
            page+=1
        if page>50: raise ValueError('Pagination safety bound exceeded.')
        return current,products
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(read_category,slug):slug for slug in known}
        for future in as_completed(futures):
            slug=futures[future]
            try:
                row,products=future.result()
                categories[slug]={'source_id':str(row.get('id') or row.get('code') or slug),'slug':slug,'name':row['name'],'parent_id':str(row.get('parentId','0')),'image':row.get('image',''),'description':row.get('description',''),'source_url':BASE+'/categories/'+slug}
                for product in products:
                    if product.get('slug'):
                        product_slugs.add(product['slug']);product_categories.setdefault(product['slug'],set()).add(slug)
            except Exception as exc: report['failures'].append({'url':BASE+'/categories/'+slug,'error':str(exc)})
    report['categories']=sorted(categories.values(),key=lambda x:x['slug'])
    print(f'Discovered {len(categories)} categories and {len(product_slugs)} unique product URLs.', flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_api, '/products/productDetails/', {'slug':slug,'dummy':False}):slug for slug in sorted(product_slugs)}
        for future in as_completed(futures):
            slug = futures[future]; url = BASE+'/products/'+slug
            try:
                info = future.result().get('productInfo',{})
                if not info.get('name'): raise ValueError('Missing public product details.')
                cats = sorted(product_categories.get(slug,set()))
                scheduled = any(re.search(r'breakfast|lunch|dinner|daily-food|monday|tuesday|wednesday|thursday|friday|saturday|sunday|chaturthi|jeyanthi|jayanth|viradham|neivedhyam',cat,re.I) for cat in cats)
                price = amount(info.get('sellingPrice'))
                photos = images(info)
                variants = info.get('variantCombinations') or []
                reasons=[]
                if scheduled: reasons.append('Owner must confirm dates, windows and schedule.')
                if price is None and not variants: reasons.append('Missing valid price.')
                if not photos: reasons.append('Missing product photography.')
                if info.get('subscribable') or info.get('addons'): reasons.append('Source subscription/add-on rules require review.')
                report['products'].append({'source_url':url,'source_id':info.get('code') or slug,'slug':slug,'name':unescape(info['name']).strip(), 'description':info.get('description',''),'short_description':info.get('shortDescription',''), 'price':price,'regular_price':amount(info.get('originalPrice')), 'available':bool(info.get('available')), 'images':photos, 'categories':cats,'fulfilment':'scheduled_meal' if scheduled else 'packaged_goods', 'variants':variants,'variant_options':info.get('variantOptions',[]),'variant_values':info.get('variants',{}),'review_reasons':reasons})
            except Exception as exc: report['failures'].append({'url':url,'error':str(exc)})
    # Pages are imported as drafts: don't carry third-party scripts or old policy promises into a published store.
    for path in ['/aboutus','/contactus','/privacy-policy','/terms-and-conditions','/refund-policy','/shipping']:
        try:
            page = state_from_html(fetch(BASE+path))['PageData']['currentPage']
            report['pages'].append({'source_url':BASE+path,'slug':path.strip('/'),'source_page':page})
        except Exception as exc: report['failures'].append({'url':BASE+path,'error':str(exc)})
    campaign_images=set()
    for component in walk(state.get('PageData',{})):
        if component.get('componentType') not in {'Banner','Carousel','Image Banner','Slider'}: continue
        for row in walk(component.get('data',{})):
            for key in ['img','image','imageUrl','src','desktopImage','mobileImage']:
                url=row.get(key)
                if isinstance(url,str) and url.startswith('https://cdn.commmerce.com/uploads/annams/wbImages/'):
                    campaign_images.add(url)
    for url in sorted(campaign_images):
        report['campaigns'].append({'image':url,'source_url':BASE,'status':'draft','reason':'Campaign dates and claims require owner review; never automatically published.'})
    report['products'].sort(key=lambda x:x['slug'])
    assets = {x for product in report['products'] for x in product['images']}
    assets.update(x['image'] for x in report['categories'] if x['image'])
    if isinstance(report['brand']['logo'],str): assets.add(report['brand']['logo'])
    assets.update(x['image'] for x in report['campaigns'])
    asset_root=ROOT/'data/assets'; asset_root.mkdir(parents=True, exist_ok=True)
    asset_map={}
    def download(url):
        ext=Path(urlsplit(url).path).suffix.lower()
        if ext not in {'.jpg','.jpeg','.png','.webp','.gif'}: raise ValueError('Unsupported image format.')
        filename=sha256(url.encode()).hexdigest()[:24]+ext
        path=asset_root/filename
        if not path.exists(): path.write_bytes(fetch(url,binary=True))
        return url,filename
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(download,url):url for url in sorted(assets)}
        for future in as_completed(futures):
            try:
                url,filename=future.result(); asset_map[url]=filename
            except Exception as exc: report['failures'].append({'url':futures[future],'error':str(exc)})
    report['assets']=asset_map
    report['summary']={'categories':len(report['categories']),'products':len(report['products']),'assets':len(asset_map),'needs_review':sum(bool(x['review_reasons']) for x in report['products']),'failures':len(report['failures'])}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    (ROOT/'reports/source-import-summary.json').write_text(json.dumps({'summary':report['summary'],'failures':report['failures'],'source':BASE,'fetched_at':report['fetched_at']},indent=2))
    print(json.dumps(report['summary'],indent=2))

if __name__=='__main__': main()
