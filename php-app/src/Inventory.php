<?php
declare(strict_types=1);
namespace Annam;

/** Optional stock, with exact dated meal buckets and order-linked reservations. */
final class Inventory {
    private static ?\WeakMap $ready=null;
    public function __construct(private Store $store){self::ensure($store->db);}
    public static function ensure(Database $db):void {
        self::$ready??=new \WeakMap();if(isset(self::$ready[$db]))return;
        $db->transaction(function()use($db){if(!$db->isSqlite())$db->one("SELECT pg_advisory_xact_lock(hashtext('annam-inventory-v1'))");$db->schemaScript(file_get_contents(ANNAM_ROOT.'/resources/inventory-'.($db->isSqlite()?'sqlite':'postgres').'.sql'));});self::$ready[$db]=true;
    }
    private static function key(int $id,?string $date,?int $slot):string{return $date&&$slot?'m:'.$date.':'.$slot.':'.$id:'p:'.$id;}
    public function state(array $item,?string $date=null,?int $slot=null):array {
        if($item['fulfilment']==='scheduled'&&(!$date||!$slot))return ['tracked'=>false,'remaining'=>0,'revision'=>0];
        $key=self::key((int)$item['id'],$item['fulfilment']==='scheduled'?$date:null,$item['fulfilment']==='scheduled'?$slot:null);
        return $this->store->db->one('SELECT * FROM catalog_inventorybucket WHERE tenant_id=? AND bucket_key=?',[$this->store->id(),$key])??['tracked'=>false,'remaining'=>0,'revision'=>0];
    }
    public function decorate(array $items,?string $date=null,?int $slot=null):array {
        if(!$items)return $items;$ids=array_column($items,'id');$params=[$this->store->id(),...$ids];$where='slot_id IS NULL';if($date&&$slot){$where.=' OR (slot_id=? AND on_date=?)';array_push($params,$slot,$date);}
        $rows=$this->store->db->rows('SELECT * FROM catalog_inventorybucket WHERE tenant_id=? AND item_id IN ('.implode(',',array_fill(0,count($ids),'?')).') AND ('.$where.')',$params);$map=[];foreach($rows as $row)$map[$row['bucket_key']]=$row;
        foreach($items as &$item){$key=$item['fulfilment']==='courier'?self::key((int)$item['id'],null,null):($date&&$slot?self::key((int)$item['id'],$date,$slot):'');$row=$map[$key]??[];$item['quantity_tracked']=(bool)($row['tracked']??false);$item['stock_quantity']=(int)($row['remaining']??0);$item['stock_revision']=(int)($row['revision']??0);}unset($item);return $items;
    }
    public static function check(array $item,int $quantity):void {if(!empty($item['quantity_tracked'])&&$quantity>(int)$item['stock_quantity'])throw new HttpError(422,'Not enough stock for '.$item['name'].'. Available: '.$item['stock_quantity'].'.');}
    public function configure(int $id,?string $date,?int $slot,bool $tracked,mixed $quantity,string $mode,int $revision):void {
        $item=$this->store->item($id);if(!in_array($mode,['set','add'],true))throw new HttpError(422,'Choose set quantity or add stock.');
        if($item['fulfilment']==='scheduled'){$date=Store::date($date??'');if($date<date('Y-m-d'))throw new HttpError(422,'Past meal quantities cannot be edited.');$this->store->slot($slot??0);}else{$date=null;$slot=null;}
        $q=filter_var($quantity,FILTER_VALIDATE_INT);if($tracked&&($q===false||$q<0||$q>1000000000))throw new HttpError(422,'Enter a whole quantity from 0 to 1000000000.');
        $this->store->db->transaction(function()use($id,$date,$slot,$tracked,$q,$mode,$revision){
            $this->store->lock();$key=self::key($id,$date,$slot);$row=$this->store->db->one('SELECT * FROM catalog_inventorybucket WHERE tenant_id=? AND bucket_key=? FOR UPDATE',[$this->store->id(),$key]);
            if((int)($row['revision']??0)!==$revision)throw new HttpError(409,'Stock changed since this form opened. Latest stock is shown; review it before saving again.');
            $remaining=$tracked?($mode==='add'?(int)($row['remaining']??0)+$q:$q):(int)($row['remaining']??0);if($remaining>1000000000)throw new HttpError(422,'The resulting quantity is too large.');
            if($row)$this->store->db->rows('UPDATE catalog_inventorybucket SET tracked=?,remaining=?,revision=revision+1 WHERE tenant_id=? AND id=?',[$tracked,$remaining,$this->store->id(),$row['id']]);
            else $this->store->db->rows('INSERT INTO catalog_inventorybucket(tenant_id,item_id,bucket_key,slot_id,on_date,tracked,remaining,revision) VALUES(?,?,?,?,?,?,?,1)',[$this->store->id(),$id,$key,$slot,$date,$tracked,$remaining]);
            if($date&&$slot){
                // A quantity edit must not freeze or replace the rest of a daily menu.
                $effective=$this->store->effectiveMenuRows($date,$slot)[$id]??null;
                $exact=$this->store->db->one("SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND item_id=? AND slot_id=? AND mode='date' AND on_date=?",[$this->store->id(),$id,$slot,$date]);
                if($exact)$this->store->db->rows('UPDATE catalog_menuschedule SET qty_limit=NULL WHERE tenant_id=? AND id=?',[$this->store->id(),$exact['id']]);
                elseif(!$effective||$effective['qty_limit']!==null)$this->store->db->rows("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,?,NULL,0,?)",[$this->store->id(),$id,$slot,$date,$effective['available']??false,$effective['price_override']??null]);
            }
        });
    }
    public function reserve(int $orderId,array $quote,string $channel):void {
        $this->store->db->transaction(function()use($orderId,$quote,$channel){
            $this->store->lock();$this->store->row('orders_order',$orderId);
            if(!$this->store->db->one('INSERT INTO orders_inventoryclaim(tenant_id,order_id) VALUES(?,?) ON CONFLICT(tenant_id,order_id) DO NOTHING RETURNING id',[$this->store->id(),$orderId]))return;
            foreach($quote['lines'] as $line){
                $item=$this->store->item((int)$line['item_id']);$quantity=(int)$line['quantity'];if(!$item['active']||!$item['in_stock'])throw new HttpError(409,'An item is no longer in stock.');$date=null;$slot=null;$schedule=null;
                if($item['fulfilment']==='scheduled'){
                    $date=$quote['date']??date('Y-m-d');$meal=$line['meal_key']??'unclassified';$slot=$this->store->db->one('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$meal]);
                    if(!$slot){$tracked=$this->store->db->one('SELECT id FROM catalog_inventorybucket WHERE tenant_id=? AND item_id=? AND on_date=? AND tracked',[$this->store->id(),$item['id'],$date]);if($tracked)throw new HttpError(422,'Choose the meal and delivery date for '.$item['name'].'.');}
                    else{
                        $entry=$this->store->effectiveMenuRows($date,(int)$slot['id'])[(int)$item['id']]??null;
                        if($channel==='web'&&(!$entry||!$entry['active']||!$entry['in_stock']||!$entry['available']))throw new HttpError(409,'A dish is no longer available. Review your cart.');
                        if($entry&&($channel==='web'||$entry['qty_limit']!==null))$schedule=$this->store->inventorySchedule($date,(int)$slot['id'],$entry);
                    }
                }
                $bucket=$this->state($item,$date,$slot?(int)$slot['id']:null);$bucketId=!empty($bucket['tracked'])?(int)$bucket['id']:null;
                if(!$bucketId&&!$schedule)continue;$key=$bucketId?'bucket:'.$bucketId:'schedule:'.$schedule;
                // Creation retries return the original order before reaching here. Aggregate
                // duplicate lines into the same ledger entry without losing their quantity.
                if($bucketId){$updated=$this->store->db->one('UPDATE catalog_inventorybucket SET remaining=remaining-?,revision=revision+1 WHERE tenant_id=? AND id=? AND tracked AND remaining>=? RETURNING id',[$quantity,$this->store->id(),$bucketId,$quantity]);if(!$updated)throw new HttpError(409,'Not enough stock for '.$item['name'].'. Reload quantities before saving.');}
                if($schedule){$updated=$this->store->db->one('UPDATE catalog_menuschedule SET qty_sold=qty_sold+? WHERE tenant_id=? AND id=? AND (qty_limit IS NULL OR qty_sold+?<=qty_limit) RETURNING id',[$quantity,$this->store->id(),$schedule,$quantity]);if(!$updated)throw new HttpError(409,'Not enough portions for '.$item['name'].'.');}
                $this->store->db->rows('INSERT INTO orders_stockreservation(tenant_id,order_id,reservation_key,bucket_id,schedule_id,quantity,released) VALUES(?,?,?,?,?,?,FALSE) ON CONFLICT(tenant_id,order_id,reservation_key) DO UPDATE SET quantity=orders_stockreservation.quantity+excluded.quantity',[$this->store->id(),$orderId,$key,$bucketId,$schedule,$quantity]);
            }
        });
    }
    public function release(int $orderId):void {
        $this->store->db->transaction(function()use($orderId){
            $this->store->row('orders_order',$orderId);$rows=$this->store->db->rows('UPDATE orders_stockreservation SET released=TRUE,released_at=CURRENT_TIMESTAMP WHERE tenant_id=? AND order_id=? AND NOT released RETURNING *',[$this->store->id(),$orderId]);
            foreach($rows as $row){if($row['bucket_id'])$this->store->db->rows('UPDATE catalog_inventorybucket SET remaining=remaining+?,revision=revision+1 WHERE tenant_id=? AND id=?',[(int)$row['quantity'],$this->store->id(),$row['bucket_id']]);if($row['schedule_id'])$this->store->db->rows('UPDATE catalog_menuschedule SET qty_sold=CASE WHEN qty_sold>=? THEN qty_sold-? ELSE 0 END WHERE tenant_id=? AND id=?',[(int)$row['quantity'],(int)$row['quantity'],$this->store->id(),$row['schedule_id']]);}
        });
    }
}
