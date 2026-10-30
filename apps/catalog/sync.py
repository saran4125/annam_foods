"""Apply a reviewed Annam catalog snapshot once, without rewriting past sales."""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from apps.tenancy.context import get_current_tenant
from apps.tenancy.models import Tenant, TenantConfig
from apps.content.models import Banner
from .models import MenuCategory, MenuItem, MenuSchedule, MenuDay, Slot, CatalogSyncRun
from .services import category_family_ids

MANIFEST = Path(settings.BASE_DIR) / 'deploy/annam_catalog_sync_20261030.json'
# Spelling/label differences already present in the old source export. Never fuzzy-match prices.
ALIASES = {
    'Ulundhu Appalam - Jeera': ['Ulundhu Applam- Jeera'],
    'Karuppu Ellu Idly Podi': ['Karuppu Elllu Idly Podi'],
    'Wheat Rava Uppma Mix': ['Wheat Rava Uppum Mix'],
    'Multigrain Millet Dosa Mix': ['Multi Grain Millet Dosa Mix'],
    'Idly with Vadai': ['Idly With Vadai'],
    'Chapathi (1)': ['Chapapthi (1)'],
}
CATEGORY_PARENTS = {
    'Murukku':'Pakshanams', 'Mixture':'Pakshanams', 'Chips':'Pakshanams', 'Thattai':'Pakshanams',
    'Halwa':'Sweets', 'Kitchen Podis':'Podi', 'Rice Mix Podi':'Podi', 'Rice Mix Herbal Podi':'Podi',
    'Rasam Paste':'Pickles', 'Rice Mix Paste':'Pickles',
    'Diwali Combos':'Diwali 2026', 'Diwali Sweets':'Diwali 2026', 'Diwali Karams':'Diwali 2026',
}


def normal_name(value):
    value = re.sub(r'^\d{1,2}(?:st|nd|rd|th|tth)\s+', '', value, flags=re.I)
    value = re.sub(r'^(?:Bf|Dr)\s*-?\s+', '', value, flags=re.I)
    value = re.sub(r'^Sing(?:le|el) Pack\s*-\s*', '', value, flags=re.I)
    if value.casefold() in ('with rice', 'without rice'):
        value = 'Full meals ' + value
    value = value.casefold()
    for old,new in [('spl ', 'special '), ('pakshanms', 'pakshanams'), ('chapapthi','chapathi'),
                    ('mixutre','mixture'),('leavs','leaves'),('pck','pack'),('hawa','halwa'),
                    ('vegitable','vegetable'),('uppma','uppuma')]:
        value=value.replace(old,new)
    return re.sub(r'[^a-z0-9]', '', value)


class SnapshotSync:
    def __init__(self, data):
        self.data=data
        self.report={'created':[], 'updated':[], 'review':[], 'menus':[], 'source':data['source']}
        self.categories={}
        export=json.loads((Path(settings.BASE_DIR)/'deploy/annam_seed.json').read_text())
        self.source_ids={}
        self.export=export
        for product in export['products']:
            self.source_ids.setdefault(normal_name(product['name']),set()).add(str(product['source_id']))

    def note(self,item,text):
        if text not in item.admin_notes:
            item.admin_notes=(item.admin_notes+'\n'+text).strip()

    def category(self,name):
        if name in self.categories:
            return self.categories[name]
        categories=list(MenuCategory.objects.all())
        matches=[c for c in categories if normal_name(c.name)==normal_name(name)]
        if len(matches)>1:
            raise ValidationError(f'Ambiguous category: {name}')
        category=matches[0] if matches else MenuCategory.objects.create(name=name,slug=slugify(name))
        parent_name=CATEGORY_PARENTS.get(name)
        if parent_name:
            parent=self.category(parent_name)
            if category.parent_id!=parent.pk:
                category.parent=parent
                category.save(update_fields=['parent'])
        if name=='Diwali 2026':
            category.description='Diwali 2026 sweets & pakshanams. Delivery on 5 November and 7 November 2026.'
            category.save(update_fields=['description'])
        self.categories[name]=category
        return category

    def find(self,name,kind='courier',slot=None):
        names={normal_name(n) for n in [name,*ALIASES.get(name,[])]}
        source_ids=set().union(*(self.source_ids.get(n,set()) for n in names))
        candidates=list(MenuItem.objects.filter(fulfilment=kind).select_related('category'))
        matches=[p for p in candidates if normal_name(p.name) in names or p.retailer_id in source_ids]
        if slot and len(matches)>1:
            scheduled=[p for p in matches if p.schedule.filter(slot=slot).exists() or
                       (p.category_id and slot.key in p.category.name.casefold())]
            if scheduled:matches=scheduled
        if slot and len(matches)>1 and len({(normal_name(p.name), p.price) for p in matches}) == 1:
            # Identical dishes imported under multiple dated meal headings can
            # share a product on a new dated menu. Preserve every old row.
            matches = sorted(matches, key=lambda p: (not p.active, p.pk))[:1]
        if len(matches)>1:
            raise ValidationError(f'Ambiguous product: {name}; choose exact IDs before syncing.')
        return matches[0] if matches else None

    def product(self,row,stock,kind='courier',slot=None):
        item=self.find(row['name'],kind,slot)
        created=item is None
        if created:
            key=f"sync:{self.data['version']}:{kind}:{slot.key if slot else ''}:{slugify(row['name'])}"
            item=MenuItem(name=row['name'],price=Decimal(row['price']),fulfilment=kind,
                          retailer_id=hashlib.sha256(key.encode()).hexdigest()[:60],weight='')
            self.note(item,'Needs photo and weight — imported from owner comparison on 30 Oct 2026.')
        elif kind=='courier':
            item.price=Decimal(row['price'])
        if kind=='courier':
            category=self.category(row['category'])
            if not item.category_id or item.category_id not in category_family_ids(category):
                item.category=category
        missing = [label for label,value in [('photo',item.image),('weight',item.weight)] if not value]
        if missing:
            self.note(item,'Needs ' + ' and '.join(missing) + ' — verify before completing catalog details.')
        item.active=True
        item.in_stock=stock
        item.save()
        self.report['created' if created else 'updated'].append(item.name)
        return item

    def run(self):
        for name in CATEGORY_PARENTS:self.category(name)
        for row in self.data['in_stock']:self.product(row,True)
        for row in self.data['diwali']:self.product(row,True)
        for row in self.data['price_updates']:
            item=self.find(row['name'])
            if not item:
                raise ValidationError(f"Price update product missing: {row['name']}")
            if row['needs_confirmation']:
                text=f"Owner decision: verify pack size before changing price to ₹{row['price']}. Current price preserved."
                self.note(item,text);self.report['review'].append(row['name']+': '+text)
            else:
                item.price=Decimal(row['price']);self.report['updated'].append(item.name)
            item.save()
        for row in self.data['sold_out']:self.product(row,False)
        for name in self.data['stock_off']:
            item=self.find(name)
            if not item:raise ValidationError(f'Stock-sync product missing: {name}')
            item.in_stock=False
            item.save(update_fields=['in_stock'])
            self.report['updated'].append(item.name)
        for name in self.data['build_only']:
            item=self.find(name)
            if not item:
                self.report['review'].append(name+': build-only entry not found; no product invented.')
                continue
            self.note(item,'Build only — owner must confirm whether to keep or remove. No removal performed.')
            item.save(update_fields=['admin_notes'])
            self.report['review'].append(item.name+': owner decision; availability unchanged.')
        self.arrange_source_subcategories()
        for name in self.data['featured']:
            item=self.find(name)
            if not item:raise ValidationError(f'Featured product missing: {name}')
            item.tags=list(dict.fromkeys([*(item.tags or []),'featured']))
            item.save(update_fields=['tags'])
        # A single primary category is supported. Existing Thokku/Thuvaiyal products
        # stay in their primary group instead of creating duplicate sellable items.
        self.report['review'].append('Thokku cross-listing: primary categories retained; model has one category per product.')
        banners=Banner.objects.filter(title__icontains='diwali')
        if not banners.exists():
            Banner.objects.create(title='Diwali 2026 sweets & pakshanams',
                subtitle='Delivery on 5 Nov and 7 Nov 2026',link='/shop/diwali-2026/')
        else:banners.update(link='/shop/diwali-2026/')
        self.daily_menu()
        return self.report

    def arrange_source_subcategories(self):
        """Use recorded source memberships for the approved hierarchy, never name guesses."""
        approved={normal_name(name):name for name in CATEGORY_PARENTS if not name.startswith('Diwali ')}
        groups={row['slug']:self.category(approved[normal_name(row['name'])])
                for row in self.export['categories'] if normal_name(row['name']) in approved}
        items={item.retailer_id:item for item in MenuItem.objects.filter(fulfilment='courier')}
        for row in self.export['products']:
            item=items.get(str(row['source_id']))
            if not item:continue
            for slug in row.get('categories',[]):
                child=groups.get(slug)
                if child and item.category_id==child.parent_id:
                    item.category=child
                    item.save(update_fields=['category'])
                    break

    def daily_menu(self):
        from .daily_menus import save_daily_menu
        on_date=date.fromisoformat(self.data['daily_menu']['date'])
        if on_date<timezone.localdate():
            self.report['review'].append(f'Dated menu {on_date} is in the past; not applied.')
            return
        for key,rows in self.data['daily_menu']['slots'].items():
            slot,_=Slot.objects.get_or_create(key=key,defaults={'label':key.title(),'order_cutoff':'23:59:59'})
            if MenuDay.objects.filter(slot=slot,on_date=on_date).exists():
                self.report['review'].append(f'{on_date} {key}: existing staff-saved menu preserved.')
                continue
            products=[]
            for row in rows:
                item=self.product(row,True,kind='scheduled',slot=slot)
                products.append((item,row))
            save_daily_menu(slot=slot,on_date=on_date,item_ids=[p.pk for p,r in products],revision=0)
            for item,row in products:
                MenuSchedule.objects.filter(slot=slot,on_date=on_date,item=item,mode='date').update(price_override=Decimal(row['price']))
            self.report['menus'].append({'date':str(on_date),'slot':key,'items':len(products)})
        for name in self.data['daily_review']:
            # Only notes; no inferred weekly menu changes.
            for item in MenuItem.objects.filter(fulfilment='scheduled'):
                if normal_name(item.name)==normal_name(name):
                    self.note(item,'Owner decision: build-only daily dish; recurring availability unchanged.')
                    item.save(update_fields=['admin_notes'])


@transaction.atomic
def sync_catalog(*,apply=False,path=MANIFEST):
    tenant=get_current_tenant()
    raw=Path(path).read_bytes();data=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
    if tenant is None or tenant.slug!=data['tenant_slug']:
        raise ValidationError('This reviewed snapshot is for the configured store only.')
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    previous=CatalogSyncRun.objects.filter(version=data['version']).first()
    if previous:
        if previous.digest!=digest:raise ValidationError('An applied sync version cannot be changed. Use a new reviewed version.')
        return {'already_applied':True,'version':previous.version,'report':previous.report}
    TenantConfig.objects.get_or_create(tenant=tenant)
    fields=['id','name','price','category_id','in_stock','active','weight']
    before={row['id']:row for row in MenuItem.objects.values(*fields)}
    report=SnapshotSync(data).run()
    report['changes']=[]
    for row in MenuItem.objects.values(*fields):
        previous_values=before.get(row['id'])
        if previous_values!=row:
            def serial(values):
                return {k:str(v) if isinstance(v,Decimal) else v for k,v in values.items()} if values else None
            report['changes'].append({'before':serial(previous_values),'after':serial(row)})
    if apply:
        CatalogSyncRun.objects.create(version=data['version'],digest=digest,report=report)
    else:transaction.set_rollback(True)
    return {'already_applied':False,'applied':apply,'version':data['version'],'report':report}


def audit_catalog_snapshot():
    """Compare the stored catalog to the uploaded snapshot, without pretending it is live scraping."""
    data=json.loads(MANIFEST.read_text())
    finder=SnapshotSync(data)
    differences=[]
    for group,stock in [('in_stock',True),('diwali',True),('sold_out',False)]:
        for row in data[group]:
            item=finder.find(row['name'])
            if not item or item.in_stock!=stock or item.price!=Decimal(row['price']) or (stock and not item.active):
                differences.append({'product':row['name'],'requirement':group})
    for name in data['stock_off']:
        item=finder.find(name)
        if not item or item.in_stock:differences.append({'product':name,'requirement':'stock_off'})
    for row in data['price_updates']:
        if row['needs_confirmation']:continue
        item=finder.find(row['name'])
        if not item or item.price!=Decimal(row['price']):differences.append({'product':row['name'],'requirement':'price'})
    for name in data['featured']:
        item=finder.find(name)
        if not item or 'featured' not in item.tags:differences.append({'product':name,'requirement':'featured'})
    if not Banner.objects.filter(title__icontains='diwali',link='/shop/diwali-2026/').exists():
        differences.append({'requirement':'diwali_banner'})
    from .services import resolve_menu
    on_date=date.fromisoformat(data['daily_menu']['date'])
    for key,rows in data['daily_menu']['slots'].items():
        slot=Slot.objects.filter(key=key).first()
        entries=resolve_menu(on_date,slot) if slot else []
        actual={(normal_name(entry.item.name),entry.price) for entry in entries}
        expected={(normal_name(row['name']),Decimal(row['price'])) for row in rows}
        if actual!=expected:differences.append({'requirement':'dated_menu','date':str(on_date),'meal':key})
    return {'version':data['version'],'comparison':'uploaded owner snapshot, not a fresh live-site crawl',
            'external_live_verified':False,'differences':differences,
            'pending_owner_decisions':['Mavadu Karam pack size/price',*data['build_only'],'Thokku cross-listing']}
