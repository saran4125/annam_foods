#!/usr/bin/env python3
"""Discover public Annam image URLs. No login, customer, cart or checkout calls."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from importlib.util import spec_from_file_location, module_from_spec
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('annam_public_source', ROOT/'wordpress/scripts/fetch_annam.py')
source = module_from_spec(spec); spec.loader.exec_module(source)
BASE = 'https://www.annamfood.in'


def public_image_url(value):
    url = urljoin(BASE+'/', unescape(value.strip()))
    parsed = urlsplit(url)
    if (parsed.scheme == 'https' and parsed.hostname in {'cdn.commmerce.com', 'www.annamfood.in', 'annamfood.in'}
            and not parsed.username and not parsed.password and parsed.port is None
            and re.search(r'\.(?:jpe?g|png|webp|gif|avif|ico)$', parsed.path, re.I)):
        return url
    return None


def image_urls(value):
    result = set()
    def add(candidate):
        if url := public_image_url(candidate): result.add(url)
    def visit(v):
        if isinstance(v, dict):
            for child in v.values(): visit(child)
        elif isinstance(v, list):
            for child in v: visit(child)
        elif isinstance(v, str):
            text = unescape(v.replace('\\/', '/'))
            if text.startswith(('https://', '/')) and not any(c.isspace() for c in text): add(text)
            for url in re.findall(r"https://(?:cdn\.commmerce\.com|www\.annamfood\.in|annamfood\.in)/[^\s<>\"'\\)]+", text): add(url)
            for value in re.findall(r"(?:src|href|srcset)\s*=\s*[\"']([^\"']+)[\"']", text, re.I):
                for part in value.split(','):
                    if part.strip(): add(part.strip().split()[0])
            for value in re.findall(r"url\(\s*[\"']?([^\"'()\s]+)", text, re.I): add(value)
    visit(value)
    return result


def fetch_page(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.annamfood.in', 'annamfood.in'}:
        raise ValueError('Not a public Annam page.')
    request = Request(url, headers={'User-Agent':'Mozilla/5.0 (Annam Foods public media recovery)'})
    with urlopen(request, timeout=35) as response:
        final = urlsplit(response.url)
        if final.scheme != 'https' or final.hostname not in {'www.annamfood.in', 'annamfood.in'}:
            raise ValueError('Unexpected public-page redirect.')
        body = response.read(12*1024*1024+1)
        if len(body)>12*1024*1024: raise ValueError('Public page exceeds 12 MB.')
        return body.decode('utf-8')


def main():
    result = {'source': BASE, 'fetched_at': datetime.now(timezone.utc).isoformat(),
              'purpose': 'Public image discovery only; never imports prices, menus, orders or customers.',
              'brand': {}, 'categories': [], 'products': [], 'media_urls': [], 'failures': []}
    urls = set(); product_slugs = set(); categories = {}
    def failure(url, error):
        result['failures'].append({'url': url, 'error': str(error)[:240]})
    try:
        html = fetch_page(BASE+'/'); urls.update(image_urls(html))
        state = source.state_from_html(html); urls.update(image_urls(state))
        store = state.get('StoreData', {}).get('storeData', {})
        result['brand'] = {key: public_image_url(store[key]) for key in ['logo', 'favicon']
                           if isinstance(store.get(key), str) and public_image_url(store[key])}
        links = source.Links(); links.feed(html)
        pages = {BASE+urlsplit(link).path for link in links.links
                 if urlsplit(link).path.startswith(('/aboutus', '/contactus', '/privacy', '/refund', '/shipping', '/terms'))}
    except Exception as error:
        failure(BASE+'/', error); pages = set()
    try:
        roots = source.fetch_api('/category/getCategories/', {'dummy': False})
        urls.update(image_urls(roots))
        categories = {row['slug']: row for row in source.walk(roots.get('categories', []))
                      if row.get('slug') and row.get('name')}
    except Exception as error:
        failure(source.PUBLIC_API+'/category/getCategories/', error)
    if len(categories)>500: raise ValueError('Public category discovery exceeded 500 categories.')
    def category(slug):
        detail = source.fetch_api('/category/getCategories/', {'category': slug, 'dummy': False})
        current = detail.get('category') or categories[slug]; products = []; found_urls = image_urls(detail)
        for page in range(1, 51):
            listing = source.fetch_api('/products/productList/', {'page': page, 'limit': 100, 'category': slug, 'sort': 'featured', 'filter': None})
            chunk = listing.get('products', []); products.extend(chunk); found_urls.update(image_urls(listing))
            total = int(listing.get('total_products') or 0)
            if not chunk or len(products)>=total: break
        else: raise ValueError('Public catalog pagination exceeded 50 pages.')
        return current, products, found_urls
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(category, slug): slug for slug in sorted(categories)}
        for task in as_completed(futures):
            slug = futures[task]
            try:
                info, products, images = task.result(); urls.update(images)
                result['categories'].append({'source_id': str(info.get('id') or info.get('code') or slug),
                    'slug': slug, 'name': info.get('name', slug), 'image': info.get('image') or ''})
                product_slugs.update(p['slug'] for p in products if p.get('slug'))
            except Exception as error: failure(BASE+'/categories/'+slug, error)
    if len(product_slugs)>3000: raise ValueError('Public product discovery exceeded 3,000 products.')
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(source.fetch_api, '/products/productDetails/', {'slug': slug, 'dummy': False}): slug
                   for slug in sorted(product_slugs)}
        for task in as_completed(futures):
            slug = futures[task]
            try:
                info = task.result().get('productInfo', {}); urls.update(image_urls(info))
                if not info.get('name'): raise ValueError('Missing public product name.')
                result['products'].append({'source_id': str(info.get('code') or slug), 'slug': slug,
                    'name': unescape(info['name']).strip(), 'images': source.images(info)})
            except Exception as error: failure(BASE+'/products/'+slug, error)
        futures = {pool.submit(fetch_page, page): page for page in sorted(pages)}
        for task in as_completed(futures):
            try: urls.update(image_urls(task.result()))
            except Exception as error: failure(futures[task], error)
    if len(urls)>5000: raise ValueError('Public image discovery exceeded 5,000 URLs.')
    result['media_urls'] = sorted(urls)
    result['categories'].sort(key=lambda x:x['slug']); result['products'].sort(key=lambda x:x['slug'])
    output = ROOT/'php-app/resources/live-public-media-source.json'
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'categories': len(result['categories']), 'products': len(result['products']),
                      'public_image_urls': len(urls), 'discovery_failures': len(result['failures'])}), flush=True)


if __name__ == '__main__': main()
