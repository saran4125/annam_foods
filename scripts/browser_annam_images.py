#!/usr/bin/env python3
"""Read public storefront pages in Chromium; save public image metadata only."""
import asyncio, json, re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urljoin
from playwright.async_api import async_playwright
from scrape_annam_media import image_urls, public_image_url, source, BASE
ROOT=Path(__file__).resolve().parents[1]

async def main():
    snapshot={'fetched_at':datetime.now(timezone.utc).isoformat(),'products':[], 'categories':[], 'media_urls':[], 'pages':[], 'failures':[], 'our_pages':[]}
    products={}; urls=set(); category_slugs=set(); product_links=set()
    old=json.loads((ROOT/'php-app/resources/live-public-media-source.json').read_text())
    category_slugs.update(c['slug'] for c in old['categories'])
    category_slugs.update(c['slug'] for c in json.loads((ROOT/'php-app/resources/source-catalog.json').read_text())['categories'])
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(viewport={'width':1440,'height':1000})
        async def response(resp):
            if urlsplit(resp.url).hostname not in {'annams.commmerce.com','www.annamfood.in','annamfood.in'}: return
            if '/store/api/' not in resp.url or not any(x in resp.url for x in ['/products/productList/','/products/productDetails/','/category/getCategories/']): return
            if resp.status!=200: return
            try:
                data=await resp.json();urls.update(image_urls(data))
                for row in source.walk(data):
                    if row.get('name') and (row.get('code') or row.get('slug')) and isinstance(row.get('images'),list):
                        images=source.images(row)
                        if images:
                            key=str(row.get('code') or row['slug'])
                            products[key]={'source_id':key,'name':row['name'],'images':images}
                    if row.get('slug') and row.get('name') and 'parentId' in row:
                        category_slugs.add(row['slug'])
            except Exception: pass
        context.on('response',response)
        async def visit(url, ours=False, screenshot=None):
            page=await context.new_page()
            try:
                res=await page.goto(url,wait_until='domcontentloaded',timeout=45000)
                await page.wait_for_timeout(2500)
                prior=-1
                for _ in range(20):
                    count=await page.locator('img').count()
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)');await page.wait_for_timeout(650)
                    if count==prior: break
                    prior=count
                data=await page.evaluate('''() => ({images:[...document.images].map(i=>({src:i.currentSrc||i.src,alt:i.alt,context:(i.closest('a')||i.parentElement)?.innerText?.slice(0,250)||'',loaded:i.complete&&i.naturalWidth>0})),links:[...document.querySelectorAll('a[href]')].map(a=>a.href)})''')
                if ours:
                    snapshot['our_pages'].append({'url':url,'status':res.status if res else 0,'images':data['images']})
                else:
                    urls.update(image_urls(await page.content()))
                    for img in data['images']:
                        if u:=public_image_url(img['src']):urls.add(u)
                    for link in data['links']:
                        parsed=urlsplit(link)
                        if parsed.hostname not in {'annamfood.in','www.annamfood.in'}:continue
                        if parsed.path.startswith('/categories/'):
                            category_slugs.add(parsed.path.removeprefix('/categories/').strip('/'))
                        if parsed.path.startswith('/products/'):product_links.add(BASE+parsed.path)
                    snapshot['pages'].append({'url':url,'status':res.status if res else 0,'images':data['images']})
                if screenshot:
                    await page.evaluate('window.scrollTo(0,0)');await page.screenshot(path=str(ROOT/screenshot),full_page=True)
                print(('ours ' if ours else 'source ')+url+' images='+str(len(data['images']))+' products='+str(len(products)),flush=True)
            except Exception as e:snapshot['failures'].append({'url':url,'error':str(e)[:200]})
            finally:await page.close()
        await visit(BASE+'/')
        seen=set()
        while category_slugs-seen:
            batch=sorted(category_slugs-seen);seen.update(batch)
            if len(seen)>150:raise RuntimeError('Category limit exceeded')
            for i in range(0,len(batch),3):
                await asyncio.gather(*(visit(BASE+'/categories/'+slug) for slug in batch[i:i+3]))
        # Product pages provide full-size galleries and names when listings omit them.
        if len(product_links)>1500:raise RuntimeError('Product limit exceeded')
        links=sorted(product_links)
        for i in range(0,len(links),4):await asyncio.gather(*(visit(url) for url in links[i:i+4]))
        await visit('https://annam-foods.onrender.com/shop/',ours=True)
        await visit('https://annam-foods.onrender.com/shop/diwali-2026/',ours=True)
        await browser.close()
    snapshot['products']=sorted(products.values(),key=lambda x:x['source_id']);snapshot['media_urls']=sorted(urls)
    (ROOT/'php-app/resources/browser-public-media-source.json').write_text(json.dumps(snapshot,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'products':len(products),'source_pages':len(snapshot['pages']),'image_urls':len(urls),'failures':len(snapshot['failures'])}),flush=True)

if __name__=='__main__':asyncio.run(main())
