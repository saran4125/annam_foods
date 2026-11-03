#!/usr/bin/env python3
"""Preserve the storefront's existing public image URLs using verified originals."""
import hashlib,json,re,shutil
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
def main():
    manifest=json.loads((ROOT/'php-app/resources/public-media.json').read_text());written=0
    for a in manifest['assets'].values():
        if a.get('status')!='downloaded':continue
        source=ROOT/'media'/a['path']
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=a.get('sha256'):continue
        suffix=Path(urlsplit(a['url']).path).suffix.lower()
        if suffix not in {'.jpg','.jpeg','.png','.webp','.gif','.avif','.ico'}:continue
        folders={r['kind'] for r in a['references']}&{'product','category'}
        aliases=[]
        for folder in folders:
            name=('menu' if folder=='product' else 'categories')+'/'+hashlib.sha256(a['url'].encode()).hexdigest()[:24]+suffix
            target=ROOT/'media'/name
            if not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);written+=1
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==a['sha256']:aliases.append(name)
        a['legacy_paths']=sorted(aliases)
    (ROOT/'php-app/resources/public-media.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    print(f'Original image URL aliases restored: {written}',flush=True)
if __name__=='__main__':main()
