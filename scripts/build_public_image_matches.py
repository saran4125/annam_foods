#!/usr/bin/env python3
"""Match verified source images by source identifier or unique exact product name."""
import json, re
from html import unescape
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'php-app/resources'
def key(name):return re.sub(r'[^a-z0-9]','',unescape(name).casefold())
def main():
    targets=json.loads((DATA/'public-image-targets.json').read_text())
    snapshots=[json.loads(p.read_text()) for p in [DATA/'browser-public-media-source.json',DATA/'live-public-media-source.json',DATA/'source-catalog.json'] if p.exists()]
    by_id={};by_name={};categories={}
    for snapshot in snapshots:
        for p in snapshot.get('products',[]):
            if p.get('images'):
                by_id.setdefault(str(p['source_id']),p)
                by_name.setdefault(key(p['name']),[]).append(p)
        for c in snapshot.get('categories',[]):
            if c.get('image'):categories.setdefault(c['slug'],c)
    # Rendered product images often expose the exact product name in alt text.
    # Keep these associations even when the public JSON API is unavailable.
    browser_path=DATA/'browser-public-media-source.json'
    if browser_path.exists():
        from scrape_annam_media import public_image_url
        browser=json.loads(browser_path.read_text())
        for page in browser.get('pages',[]):
            for image in page.get('images',[]):
                url=public_image_url(image.get('src',''))
                name=image.get('alt','').strip()
                if url and name:
                    by_name.setdefault(key(name),[]).insert(0,{'name':name,'images':[url]})
    aliases={'diwali-2026':'deepavli-2026-pakshanams','diwali-sweets':'deepavali-sweets','diwali-karams':'deepavali-karams'}
    legacy_by_id={str(p['source_id']):p for p in snapshots[-1].get('products',[]) if p.get('images')}
    reviewed_products={'Tapioca Chips':'TC1','Diwali - Mega Combo Pack':'MCS2','Diwali - Assorted Sweets 500gm':'DTA2','Diwali - Moru Moru Murukku':'DMM1','Mini Milagu Appalam':'MMA1','Idiyappam (4)':'TDI2'}
    matches=[];unmatched=[]
    for p in targets['products']:
        candidate=legacy_by_id.get(str(p['source_id'])) or by_id.get(str(p['source_id']));method='saved_catalog_source_id'
        if p['name'] in reviewed_products:
            candidate=by_id.get(reviewed_products[p['name']]);method='reviewed_source_spelling_or_dated_name'
        elif candidate and str(p['source_id']) not in legacy_by_id and key(candidate['name'])!=key(p['name']):
            candidate=None
        if not candidate:
            candidates=by_name.get(key(p['name']),[])
            # Prefer a fresh browser match; refuse ambiguous names with different photos.
            if candidates:
                fresh=next(([c for c in snap.get('products',[]) if c.get('images') and key(c['name'])==key(p['name'])] for snap in snapshots if any(c.get('images') and key(c['name'])==key(p['name']) for c in snap.get('products',[]))),[])
                candidates=fresh or candidates
            unique={c['images'][0] for c in candidates}
            if len(unique)==1:candidate=candidates[0];method='unique_exact_name'
        if candidate:
            matches.append({'url':candidate['images'][0],'kind':'product','source_id':p['source_id'],'name':p['name'],'image_index':0,'matched_by':method})
        else:unmatched.append({'kind':'product','name':p['name'],'source_id':p['source_id']})
    for c in targets['categories']:
        source_slug=aliases.get(c['slug'],c['slug']);candidate=categories.get(source_slug)
        if candidate:matches.append({'url':candidate['image'],'kind':'category','slug':c['slug'],'source_id':candidate['source_id'],'name':c['name'],'matched_by':'reviewed_category_alias' if source_slug!=c['slug'] else 'slug'})
        else:unmatched.append({'kind':'category','name':c['name'],'slug':c['slug']})
    # Reviewed source artwork for the existing Diwali promotional banner.
    for snapshot in snapshots:
        banner=next((u for u in snapshot.get('media_urls',[]) if re.search(r'/[0-9]+Diwali-Banner\.jpg$',u)),None)
        if banner:
            matches.append({'url':banner,'kind':'banner','title':'Diwali 2026 sweets & pakshanams','name':'Diwali promotion','matched_by':'reviewed_banner_artwork'})
            break
    report={'tenant':'annam','matches':matches,'unmatched':unmatched,'policy':'Original source ID or unambiguous exact name; explicit reviewed Diwali category aliases. No prices, menus or order changes.'}
    (DATA/'public-image-matches.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f'Image matches: {len(matches)}; unmatched: {len(unmatched)}',flush=True)
if __name__=='__main__':main()
