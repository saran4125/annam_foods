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
    urls = set(); product_slugs = set(); categories = {}; api_available = True; public_pages = set(); html_products = {}
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
        failure(source.PUBLIC_API+'/category/getCategories/', error); api_available = False
    # HTML pages expose public image data independently of the catalog API.
    # Seed saved category paths too, so an API restriction cannot truncate recovery.
    saved = json.loads((ROOT/'php-app/resources/source-catalog.json').read_text())
    queue = {BASE+'/categories'} | {BASE+'/categories/'+c['slug'] for c in saved['categories']}
    queue.update(pages)
    seen = set()
    def inspect_page(url):
        html = fetch_page(url)
        try: state = source.state_from_html(html)
        except ValueError: state = {}
        links = source.Links(); links.feed(html)
        return html, state, links.links
    with ThreadPoolExecutor(max_workers=4) as pool:
        while queue:
            batch = sorted(queue-seen); queue.clear()
            if not batch: break
            futures = {pool.submit(inspect_page, url): url for url in batch}
            for task in as_completed(futures):
                url = futures[task]; seen.add(url)
                try:
                    html, state, links = task.result(); public_pages.add(url)
                    urls.update(image_urls(html)); urls.update(image_urls(state))
                    for row in source.walk(state):
                        if row.get('slug') and row.get('name') and ('parentId' in row or ('children' in row and 'sellingPrice' not in row)):
                            categories.setdefault(row['slug'], row)
                        if row.get('name') and row.get('code') and isinstance(row.get('images'), list):
                            key = str(row['code'])
                            html_products[key] = {'source_id': key, 'slug': row.get('slug', ''),
                                'name': unescape(row['name']).strip(), 'images': source.images(row)}
                    for link in links:
                        candidate = urlsplit(urljoin(url, link))
                        if (candidate.scheme == 'https' and candidate.hostname in {'annamfood.in','www.annamfood.in'}
                                and not candidate.username and not candidate.password and candidate.port is None
                                and candidate.path.startswith(('/categories/', '/products/'))):
                            target = BASE+candidate.path.rstrip('/')
                            # Only follow pagination explicitly linked by the public site.
                            if candidate.query and re.fullmatch(r'page=\d{1,3}', candidate.query): target += '?'+candidate.query
                            if target not in seen: queue.add(target)
                except Exception as error: failure(url, error)
            if len(seen|queue)>3500: raise ValueError('Public page crawl exceeded 3,500 pages.')
    result['public_pages_crawled'] = len(public_pages)
    result['products'] = list(html_products.values())
    if not api_available:
        result['categories'] = [{'source_id': str(c.get('id') or c.get('code') or slug),
            'slug': slug, 'name': c.get('name',slug), 'image': c.get('image') or ''} for slug,c in categories.items()]

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
        futures = {pool.submit(category, slug): slug for slug in sorted(categories) if api_available}
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
                   for slug in sorted(product_slugs) if api_available}
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
    result['categories'].sort(key=lambda x:x['slug']); result['products'] = sorted({p['source_id']:p for p in result['products']}.values(), key=lambda x:x['source_id'])
    output = ROOT/'php-app/resources/live-public-media-source.json'
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'categories': len(result['categories']), 'products': len(result['products']),
                      'public_image_urls': len(urls), 'discovery_failures': len(result['failures'])}), flush=True)


if __name__ == '__main__': main()
