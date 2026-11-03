#!/usr/bin/env python3
"""Audit only public storefront pages/images and archive missing public originals."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
import hashlib,json,os,re,time
from pathlib import Path
from urllib.parse import urljoin,urlsplit
from urllib.request import Request,urlopen
from PIL import Image
BASE='https://annam-foods.onrender.com'
ROOT=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):super().__init__();self.images=set();self.links=set()
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='img' and a.get('src'):self.images.add(urljoin(BASE,a['src']))
        if tag=='a' and a.get('href'):
            url=urljoin(BASE,a['href']);p=urlsplit(url)
            if p.hostname==urlsplit(BASE).hostname and p.path.startswith('/shop/'):self.links.add(url)
def read(url,limit=15728640):
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!=urlsplit(BASE).hostname or p.port or p.username or p.password:raise ValueError('Unapproved public storefront URL')
    with urlopen(Request(url,headers={'User-Agent':'Annam Foods owner image audit'}),timeout=35) as r:
        if urlsplit(r.url).hostname!=p.hostname:raise ValueError('Unexpected redirect')
        data=r.read(limit+1)
        if len(data)>limit:raise ValueError('Public response exceeds limit')
        return data

def main():
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'pages':[],'images':[],'failures':[],'archived_files':[]}
    # Wait for Render's asynchronous deployment to expose the repaired Diwali photos.
    for attempt in range(12):
        try:
            p=Page();p.feed(read(BASE+'/shop/diwali-2026/').decode())
            if len(p.images)>10:break
        except Exception:pass
        print('Waiting for deployed Diwali image fixes',attempt+1,flush=True);time.sleep(20)
    report['deployment_image_fix_visible']=len(p.images)>10
    if not report['deployment_image_fix_visible']:report['failures'].append({'url':BASE+'/shop/diwali-2026/','error':'Deployed Diwali photo fix is not visible yet'})
    queue={BASE+'/',BASE+'/menu/',BASE+'/shop/'};seen=set();images=set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        while queue:
            batch=sorted(queue-seen);queue.clear()
            if not batch:break
            for url,result in zip(batch,pool.map(lambda u: safe_page(u),batch)):
                seen.add(url)
                if isinstance(result,Exception):report['failures'].append({'url':url,'error':str(result)});continue
                page=result;images.update(page.images);report['pages'].append(url);queue.update(page.links-seen)
            if len(seen|queue)>150:raise ValueError('Public storefront audit exceeded 150 pages')
        for url,result in zip(sorted(images),pool.map(safe_image,sorted(images))):
            if isinstance(result,Exception):report['failures'].append({'url':url,'error':str(result)});continue
            data,ext=result;digest=hashlib.sha256(data).hexdigest();parsed=urlsplit(url);relative=parsed.path.removeprefix('/media/')
            if not parsed.path.startswith('/media/') or not re.fullmatch(r'(?:menu|catalog|categories|brand|site)/[A-Za-z0-9._-]+\.(?:jpg|jpeg|png|webp|gif|avif|ico)',relative):relative='site/'+hashlib.sha256(url.encode()).hexdigest()[:32]+'.'+ext
            target=ROOT/'media'/relative
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=digest:relative='site/'+hashlib.sha256((url+digest).encode()).hexdigest()[:32]+'.'+ext;target=ROOT/'media'/relative
            if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);report['archived_files'].append('media/'+relative)
            report['images'].append({'url':url,'path':relative,'sha256':digest,'bytes':len(data)})
    report['counts']={'pages':len(report['pages']),'verified_public_images':len(report['images']),'failed_requests':len(report['failures']),'new_archived_files':len(report['archived_files'])}
    (ROOT/'docs/live-image-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['counts']),flush=True)
    if os.getenv('GITHUB_STEP_SUMMARY'):Path(os.environ['GITHUB_STEP_SUMMARY']).write_text('Live image audit\n\n'+json.dumps(report['counts']))
def safe_page(url):
    try:p=Page();p.feed(read(url).decode());return p
    except Exception as e:return e
def safe_image(url):
    try:
        data=read(url)
        with Image.open(BytesIO(data)) as image:
            ext={'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif','AVIF':'avif','ICO':'ico'}.get(image.format)
            if not ext:raise ValueError('Unsupported image format')
            image.verify()
        return data,ext
    except Exception as e:return e
if __name__=='__main__':main()
