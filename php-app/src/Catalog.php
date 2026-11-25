<?php
declare(strict_types=1);
namespace Annam;

/** Master catalog membership is separate from dated menu availability. */
final class Catalog {
    public const MEALS=['breakfast'=>'Breakfast','lunch'=>'Lunch','dinner'=>'Dinner'];
    public const DEFAULTS=self::MEALS+['shop'=>'Shop'];
    public function __construct(private Store $store){}
    public function defaults():void {
        $this->store->db->transaction(function(){
            $this->store->lock();$version='four-default-categories-v1';
            if($this->store->db->one('SELECT id FROM catalog_catalogsyncrun WHERE tenant_id=? AND version=?',[$this->store->id(),$version]))return;
            $resources=new Resources($this->store);$sort=0;
            foreach(self::DEFAULTS as $key=>$name){
                if(!$this->store->db->one('SELECT id FROM catalog_menucategory WHERE tenant_id=? AND slug=?',[$this->store->id(),$key]))$resources->save('categories',null,['name'=>$name,'slug'=>$key,'active'=>1,'sort'=>$sort]);
                if(isset(self::MEALS[$key])&&!$this->store->db->one('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$key]))$resources->save('slots',null,['label'=>$name,'key'=>$key,'active'=>1,'sort'=>$sort,'order_cutoff'=>'23:59:59']);
                $sort++;
            }
            $this->store->db->rows('INSERT INTO catalog_catalogsyncrun(tenant_id,version,digest,report,applied_at) VALUES(?,?,?,?,?)',[$this->store->id(),$version,hash('sha256',$version),'{}',date('c')]);
        });
    }
    public function meals(array $item):array {
        if($item['fulfilment']!=='scheduled')return [];$tags=json_decode($item['tags']??'[]',true)?:[];
        if(in_array('meals:assigned',$tags,true))return array_keys(array_filter(self::MEALS,fn($label,$key)=>in_array('meal:'.$key,$tags,true),ARRAY_FILTER_USE_BOTH));
        $keys=array_column($this->store->db->rows('SELECT DISTINCT s.key FROM catalog_menuschedule m JOIN catalog_slot s ON s.id=m.slot_id AND s.tenant_id=m.tenant_id WHERE m.tenant_id=? AND m.item_id=?',[$this->store->id(),$item['id']]),'key');
        if($item['category_id']){$c=$this->store->db->one('SELECT slug FROM catalog_menucategory WHERE tenant_id=? AND id=?',[$this->store->id(),$item['category_id']]);if(isset(self::MEALS[$c['slug']??'']))$keys[]=$c['slug'];}
        return array_values(array_unique($keys));
    }
    public function assign(int $id,mixed $keys):void {
        if(!is_array($keys)||count(array_filter($keys,fn($key)=>is_string($key)&&isset(self::MEALS[$key])))!==count($keys))throw new HttpError(422,'Choose Breakfast, Lunch or Dinner.');
        $this->store->db->transaction(function()use($id,$keys){$this->store->lock();$item=$this->store->item($id);if($item['fulfilment']==='scheduled'&&!$keys)throw new HttpError(422,'Select at least one meal for this dish.');
            $tags=json_decode($item['tags'],true)?:[];$tags=array_values(array_filter($tags,fn($t)=>$t!=='meals:assigned'&&!str_starts_with($t,'meal:')));$tags[]='meals:assigned';
            if($item['fulfilment']==='scheduled')foreach(array_unique($keys) as $key)$tags[]='meal:'.$key;
            $category=$item['category_id'];$current=$category?$this->store->db->one('SELECT slug FROM catalog_menucategory WHERE tenant_id=? AND id=?',[$this->store->id(),$category]):null;if(!$category||(isset(self::DEFAULTS[$current['slug']??''])&&($item['fulfilment']==='courier'?$current['slug']!=='shop':!in_array($current['slug'],$keys,true)))){$slug=$item['fulfilment']==='courier'?'shop':$keys[0];$row=$this->store->db->one('SELECT id FROM catalog_menucategory WHERE tenant_id=? AND slug=?',[$this->store->id(),$slug]);$category=$row['id']??null;}
            $this->store->db->rows('UPDATE catalog_menuitem SET tags=?,category_id=? WHERE tenant_id=? AND id=?',[json_encode($tags),$category,$this->store->id(),$id]);
        });
    }
    public function contains(array $category,array $item):bool {
        if($category['slug']==='shop')return $item['fulfilment']==='courier';
        if(isset(self::MEALS[$category['slug']]))return in_array($category['slug'],$this->meals($item),true);
        return in_array((int)$item['category_id'],$this->store->family((int)$category['id']),true);
    }
    /** Validated static keys only; values never come from untrusted SQL text. */
    public static function condition(string $meal):string {
        if(!isset(self::MEALS[$meal]))throw new HttpError(422,'Choose a meal.');
        return "(CAST(i.tags AS TEXT) LIKE '%\"meal:$meal\"%' OR (CAST(i.tags AS TEXT) NOT LIKE '%\"meals:assigned\"%' AND (EXISTS(SELECT 1 FROM catalog_menuschedule m JOIN catalog_slot s ON s.id=m.slot_id AND s.tenant_id=m.tenant_id WHERE m.tenant_id=i.tenant_id AND m.item_id=i.id AND s.key='$meal') OR EXISTS(SELECT 1 FROM catalog_menucategory c WHERE c.id=i.category_id AND c.tenant_id=i.tenant_id AND c.slug='$meal'))))";
    }
}
