<?php
declare(strict_types=1);
namespace Annam;

final class Store {
    private const TABLES = ['tenancy_tenantsecrets','orders_customer','orders_address','orders_order','orders_orderevent',
        'billing_invoice','billing_invoicesequence','billing_invoicerequest',
        'orders_couriercharge','payments_courierpayment','payments_razorpayconnection','payments_paymentintent','payments_refund','payments_paymentevent',
        'messaging_outboundmessage','messaging_whatsappconversation','messaging_whatsappmessage',
        'messaging_whatsappreceipt','messaging_whatsappforwardevent'];
    public readonly array $tenant;
    public array $config;
    public function __construct(public readonly Database $db) {
        $slug = getenv('STORE_SLUG') ?: 'annam';
        $this->tenant = $db->one('SELECT * FROM tenancy_tenant WHERE slug=? AND status=?', [$slug, 'active'])
            ?? throw new HttpError(404, 'Store not found.');
        $this->config = $db->one('SELECT * FROM tenancy_tenantconfig WHERE tenant_id=?', [$this->id()])
            ?? throw new \RuntimeException('Store settings are missing.');
        foreach (['theme', 'features', 'home_sections', 'storefront_design', 'checkout_settings', 'kitchen_closed_window'] as $field) {
            $this->config[$field] = json_decode($this->config[$field] ?? '{}', true, 512, JSON_THROW_ON_ERROR);
        }
    }
    public function id(): int { return (int)$this->tenant['id']; }
    public function profile(): array {
        return $this->db->one('SELECT * FROM tenancy_billingprofile WHERE tenant_id=?', [$this->id()])
            ?? throw new HttpError(422, 'Complete the legal billing settings first.');
    }
    public function reload(): void {
        $fresh = new self($this->db); $this->config = $fresh->config;
    }
    public function lock(): void { $this->db->one('SELECT id FROM tenancy_tenant WHERE id=? FOR UPDATE', [$this->id()]); }
    public function row(string $table, int|string $id, bool $lock = false): array {
        self::table($table);
        return $this->db->one('SELECT * FROM '.$table.' WHERE tenant_id=? AND id=?'.($lock?' FOR UPDATE':''),[$this->id(),$id])
            ?? throw new HttpError(404,'Record not found.');
    }
    public function insert(string $table, array $values): array {
        self::table($table); $values['tenant_id']=$this->id();
        $columns=array_keys($values); foreach($columns as $key) self::column($key);
        return $this->db->one('INSERT INTO '.$table.'('.implode(',',array_map(fn($k)=>'"'.$k.'"',$columns)).') VALUES('.implode(',',array_fill(0,count($values),'?')).') RETURNING *',array_values($values));
    }
    public function update(string $table, int|string $id, array $values): void {
        self::table($table);
        if (isset($values['tenant_id'])||isset($values['id'])) throw new \LogicException('Record ownership cannot be changed.');
        if ($table==='billing_invoice' && array_diff(array_keys($values),['pdf','sent_customer_at','sent_owner_at'])) throw new \LogicException('Issued bills are immutable. Issue a credit note instead.');
        if ($table==='orders_order' && array_intersect(array_keys($values),['items','address','pricing','subtotal','total','delivery_fee','discount','customer_id'])) throw new \LogicException('Order snapshots are immutable.');
        foreach(array_keys($values) as $key) self::column($key);
        $sets=implode(',',array_map(fn($k)=>'"'.$k.'"=?',array_keys($values)));
        $this->db->rows('UPDATE '.$table.' SET '.$sets.' WHERE tenant_id=? AND id=?',[...array_values($values),$this->id(),$id]);
    }
    private static function table(string $name): void { if(!in_array($name,self::TABLES,true)) throw new \LogicException('Unsupported store table.'); }
    private static function column(string $name): void { if(!preg_match('/^[a-z_][a-z_0-9]*$/D',$name)) throw new \LogicException('Invalid column.'); }
    public static function json(array $row, array $fields): array { foreach($fields as $f) $row[$f]=is_string($row[$f]??null)?json_decode($row[$f],true,512,JSON_THROW_ON_ERROR):($row[$f]??[]);return $row; }
    public static function uuid(): string { $hex=bin2hex(random_bytes(16));return substr($hex,0,8).'-'.substr($hex,8,4).'-4'.substr($hex,13,3).'-'.dechex((hexdec($hex[16])&3)|8).substr($hex,17,3).'-'.substr($hex,20); }
    public function name(): string { return $this->config['brand_name'] ?: $this->tenant['name']; }
    public function slots(): array { return $this->db->rows('SELECT * FROM catalog_slot WHERE tenant_id=? AND active AND key NOT IN (\'snack\',\'snacks\') ORDER BY sort,key', [$this->id()]); }
    public function slot(int $id): array { return $this->db->one('SELECT * FROM catalog_slot WHERE tenant_id=? AND id=?', [$this->id(), $id]) ?? throw new HttpError(404, 'Meal not found.'); }
    public function items(string $kind = '', string $query = '', ?int $category = null): array {
        $sql = 'SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id WHERE i.tenant_id=?';
        $params = [$this->id()];
        if ($kind) { $sql .= ' AND i.fulfilment=?'; $params[] = $kind; }
        if ($query) { $sql .= ' AND i.name ILIKE ?'; $params[] = '%' . $query . '%'; }
        if ($category) { $ids=$this->family($category);$sql.=' AND i.category_id IN ('.implode(',',array_fill(0,count($ids),'?')).')';array_push($params,...$ids); }
        return (new Inventory($this))->decorate($this->db->rows($sql . ' ORDER BY i.sort,i.sort_priority DESC,i.name,i.id', $params));
    }
    public function pageItems(string $kind,string $query,?int $category,int $page,int $size=30,array $filters=[],string $meal='',string $sort='featured'):array {
        $inventory=new Inventory($this);
        $size=max(1,min($size,100));$params=[$this->id()];$where=' WHERE i.tenant_id=?';if($kind){$where.=' AND i.fulfilment=?';$params[]=$kind;}if($query){$where.=' AND i.name ILIKE ?';$params[]='%'.mb_substr($query,0,120).'%';}
        if($category){$family=$this->family($category);$where.=' AND i.category_id IN ('.implode(',',array_fill(0,count($family),'?')).')';array_push($params,...$family);}
        foreach(['active','in_stock'] as $field)if(array_key_exists($field,$filters)){
            if($field==='in_stock'){$empty="EXISTS(SELECT 1 FROM catalog_inventorybucket v WHERE v.tenant_id=i.tenant_id AND v.item_id=i.id AND v.slot_id IS NULL AND v.tracked AND v.remaining=0 AND i.fulfilment='courier')";$where.=$filters[$field]?' AND i.in_stock AND NOT '.$empty:' AND (NOT i.in_stock OR '.$empty.')';}
            else{$where.=' AND i.'.$field.'=?';$params[]=(bool)$filters[$field];}
        }
        if($meal){
            if(isset(Catalog::MEALS[$meal])){$where.=' AND '.Catalog::condition($meal);}
            elseif($meal==='unassigned'){
                $where.=' AND NOT ('.implode(' OR ',array_map(fn($key)=>Catalog::condition($key),array_keys(Catalog::MEALS))).')';
                $where.=" AND NOT EXISTS(SELECT 1 FROM catalog_menuschedule m WHERE m.tenant_id=i.tenant_id AND m.item_id=i.id) AND NOT EXISTS(SELECT 1 FROM catalog_menucategory c JOIN catalog_slot s ON s.key=c.slug AND s.tenant_id=c.tenant_id WHERE c.id=i.category_id AND c.tenant_id=i.tenant_id)";
            }else{
                $where.=" AND (EXISTS(SELECT 1 FROM catalog_menuschedule m JOIN catalog_slot s ON s.id=m.slot_id AND s.tenant_id=m.tenant_id WHERE m.tenant_id=i.tenant_id AND m.item_id=i.id AND s.key=?) OR EXISTS(SELECT 1 FROM catalog_menucategory c WHERE c.id=i.category_id AND c.tenant_id=i.tenant_id AND c.slug=?))";
                array_push($params,$meal,$meal);
            }
        }
        $order=match($sort){'price'=>'CAST(i.price AS DECIMAL) ASC,i.name,i.id','-price'=>'CAST(i.price AS DECIMAL) DESC,i.name,i.id','name'=>'i.name,i.id',default=>'i.sort,i.sort_priority DESC,i.name,i.id'};$total=(int)$this->db->one('SELECT COUNT(*) AS n FROM catalog_menuitem i'.$where,$params)['n'];$page=max(1,min($page,max(1,(int)ceil($total/$size))));$records=$this->db->rows('SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id'.$where.' ORDER BY '.$order.' LIMIT '.$size.' OFFSET '.(($page-1)*$size),$params);$records=(new Inventory($this))->decorate($records);return compact('records','total','page');
    }
    public function item(int $id): array {
        $row=$this->db->one('SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id WHERE i.tenant_id=? AND i.id=?', [$this->id(), $id]) ?? throw new HttpError(404, 'Dish not found.');return (new Inventory($this))->decorate([$row])[0];
    }
    public function categories(): array {
        $categories=$this->db->rows('SELECT * FROM catalog_menucategory WHERE tenant_id=? ORDER BY sort,name,id',[$this->id()]);
        $photos=[];$children=[];
        foreach($this->db->rows("SELECT category_id,image FROM catalog_menuitem WHERE tenant_id=? AND image<>'' ORDER BY active DESC,in_stock DESC,sort,id",[$this->id()]) as $item)$photos[$item['category_id']]??=$item['image'];
        foreach($categories as $category)if($category['active'])$children[$category['parent_id']][]=$category['id'];
        foreach($categories as &$category){
            if($category['image'])continue;
            $todo=[$category['id']];$seen=[];
            while($todo){$id=array_shift($todo);if(isset($seen[$id]))continue;$seen[$id]=true;if(isset($photos[$id])){$category['image']=$photos[$id];break;}array_push($todo,...($children[$id]??[]));}
        }unset($category);return $categories;
    }
    public function setItemFlag(int $id,string $field,bool $enabled):void {
        if(!in_array($field,['active','in_stock'],true))throw new HttpError(422,'Choose a valid product setting.');
        $this->item($id);
        $this->db->rows('UPDATE catalog_menuitem SET '.$field.'=? WHERE tenant_id=? AND id=?',[$enabled,$this->id(),$id]);
    }
    public function pages(): array { return $this->db->rows('SELECT * FROM content_page WHERE tenant_id=? AND published ORDER BY sort,title', [$this->id()]); }
    public function logo(): string { return image_url($this->config['theme']['logo_url'] ?? '') ?: '/media/brand/annam-logo.png'; }
    public static function date(string $value): string {
        $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        if (!$date || $date->format('Y-m-d') !== $value) throw new HttpError(422, 'Choose a valid menu date.');
        return $value;
    }
    public function carriesForward(int $slotId): bool {
        $slot=$this->slot($slotId);if(!in_array($slot['key'],['breakfast','lunch','dinner'],true))return false;
        return array_key_exists('carry_forward_meals',$this->config['features'])?($this->config['features']['carry_forward_meals']===true):true;
    }
    public function effectiveMenuRows(string $date,int $slotId):array {
        self::date($date);$this->slot($slotId);
        $day=$this->db->one('SELECT id FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?',[$this->id(),$slotId,$date]);
        $previous=!$day&&$this->carriesForward($slotId)?$this->db->one('SELECT on_date FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date<? ORDER BY on_date DESC LIMIT 1',[$this->id(),$slotId,$date]):null;
        $condition="(s.mode='date' AND s.on_date=?)";$params=[$this->id(),$slotId,$date];
        if($previous){$condition.=" OR (s.mode='date' AND s.on_date=?)";$params[]=$previous['on_date'];}
        elseif(!$day){$condition.=" OR (s.mode='weekday' AND s.weekday=?)";$params[]=(int)(new \DateTimeImmutable($date))->format('N')-1;}
        $rows=$this->db->rows('SELECT i.*,s.id AS schedule_id,s.mode,s.on_date AS source_date,s.available,s.qty_limit,s.qty_sold,s.price_override,COALESCE(s.price_override,i.price) AS effective_price FROM catalog_menuschedule s JOIN catalog_menuitem i ON i.id=s.item_id AND i.tenant_id=s.tenant_id WHERE s.tenant_id=? AND s.slot_id=? AND ('.$condition.") AND i.fulfilment='scheduled'",$params);
        $defaults=[];$dated=[];foreach($rows as $r){$r['inherited']=$r['mode']==='date'&&$r['source_date']!==$date;if($r['inherited'])$r['qty_sold']=0;if($r['mode']==='date'&&$r['source_date']===$date)$dated[(int)$r['id']]=$r;else $defaults[(int)$r['id']]=$r;}
        return array_replace($defaults,$dated);
    }
    public function menu(string $date,int $slotId,bool $includeUnavailable=false):array {
        $rows=(new Inventory($this))->decorate(array_values($this->effectiveMenuRows($date,$slotId)),$date,$slotId);
        $result=array_filter(array_values($rows),fn($r)=>$r['active']&&($includeUnavailable||($r['available']&&($r['in_stock']??true)&&(!$r['quantity_tracked']||$r['stock_quantity']>0)&&($r['qty_limit']===null||$r['qty_sold']<$r['qty_limit']))));
        usort($result,fn($a,$b)=>[$a['sort'],-$a['sort_priority'],$a['name'],$a['id']]<=>[$b['sort'],-$b['sort_priority'],$b['name'],$b['id']]);return array_values($result);
    }
    private function materializeMenu(string $date,int $slotId):void {
        if($this->db->one('SELECT id FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?',[$this->id(),$slotId,$date]))return;
        foreach($this->effectiveMenuRows($date,$slotId) as $r)if($r['mode']!=='date'||$r['source_date']!==$date)$this->db->rows("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,?,?,?,?)",[$this->id(),$r['id'],$slotId,$date,$r['available'],$r['qty_limit'],$r['qty_sold'],$r['price_override']]);
        $this->db->rows('INSERT INTO catalog_menuday(tenant_id,slot_id,on_date,revision,updated_at) VALUES(?,?,?,0,CURRENT_TIMESTAMP)',[$this->id(),$slotId,$date]);
    }
    public function inventorySchedule(string $date,int $slotId,array $entry):int {
        if(empty($entry['inherited']))return (int)$entry['schedule_id'];
        // Called while the order owns the store lock. Tomorrow's reservations
        // use their own row and never consume yesterday's daily portions.
        $row=$this->db->one("SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND item_id=? AND slot_id=? AND mode='date' AND on_date=?",[$this->id(),$entry['id'],$slotId,$date]);
        if(!$row)$row=$this->db->one("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,?,?,0,?) RETURNING id",[$this->id(),$entry['id'],$slotId,$date,$entry['available'],$entry['qty_limit'],$entry['price_override']]);
        return (int)$row['id'];
    }
    public function menuRevision(string $date, int $slotId): int {
        $row = $this->db->one('SELECT revision FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?', [$this->id(), $slotId, self::date($date)]);
        return (int)($row['revision'] ?? 0);
    }
    public function saveWeeklyMembership(int $itemId,int $slotId,array $days):void {
        $item=$this->item($itemId);$this->slot($slotId);if($item['fulfilment']!=='scheduled')throw new HttpError(422,'Weekly meal schedules require a meal dish.');
        foreach($days as $day)if(!is_scalar($day)||filter_var($day,FILTER_VALIDATE_INT)===false||(int)$day<0||(int)$day>6)throw new HttpError(422,'Choose valid weekdays.');$days=array_values(array_unique(array_map('intval',$days)));
        $this->db->transaction(function()use($itemId,$slotId,$days){$this->lock();
            foreach(range(0,6) as $day){$row=$this->db->one("SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND item_id=? AND slot_id=? AND mode='weekday' AND weekday=?",[$this->id(),$itemId,$slotId,$day]);$available=in_array($day,$days,true);
                if($row)$this->db->rows('UPDATE catalog_menuschedule SET available=? WHERE tenant_id=? AND id=?',[$available,$this->id(),$row['id']]);
                elseif($available)$this->db->rows("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'weekday',NULL,?,TRUE,NULL,0,NULL)",[$this->id(),$itemId,$slotId,$day]);
            }
        });
    }
    public function saveMenu(string $date, int $slotId, array $ids, int $revision, array $makeOrderable = []): void {
        self::date($date); $this->slot($slotId);
        if ($date < date('Y-m-d')) throw new HttpError(422, 'Historical menus cannot be changed.');
        $ids = array_values(array_unique(array_map('intval', $ids)));
        if (count($ids) > 500) throw new HttpError(422, 'Too many selected dishes.');
        $makeOrderable = array_values(array_intersect($ids, array_map('intval', $makeOrderable)));
        $this->db->transaction(function () use ($date, $slotId, $ids, $revision, $makeOrderable): void {
            // Serialize full-menu saves against the same store, including the first save.
            $this->db->one('SELECT id FROM tenancy_tenant WHERE id=? FOR UPDATE', [$this->id()]);
            if ($revision !== $this->menuRevision($date, $slotId)) throw new HttpError(409, 'This menu changed in another window. Reload it before saving.');
            foreach ($ids as $id) {
                $item = $this->item($id);
                if ($item['fulfilment'] !== 'scheduled' || (!$item['active'] && !in_array($id,$makeOrderable,true))) throw new HttpError(422, 'Choose active meal dishes only.');
            }
            // Reactivation is explicit in the picker, atomic with the menu revision check.
            foreach ($makeOrderable as $id) $this->db->rows('UPDATE catalog_menuitem SET active=TRUE,in_stock=TRUE WHERE tenant_id=? AND id=?',[$this->id(),$id]);
            $this->materializeMenu($date,$slotId);
            $this->db->rows('INSERT INTO catalog_menuday(tenant_id,slot_id,on_date,revision,updated_at) VALUES(?,?,?,1,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id,slot_id,on_date) DO UPDATE SET revision=catalog_menuday.revision+1,updated_at=CURRENT_TIMESTAMP', [$this->id(), $slotId, $date]);
            // Do not delete schedules or reset stock counters for a previously ordered dish.
            $this->db->rows('UPDATE catalog_menuschedule SET available=FALSE WHERE tenant_id=? AND slot_id=? AND mode=\'date\' AND on_date=?', [$this->id(), $slotId, $date]);
            foreach ($ids as $id) {
                $row = $this->db->one('SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND item_id=? AND slot_id=? AND mode=\'date\' AND on_date=?', [$this->id(), $id, $slotId, $date]);
                if ($row) $this->db->rows('UPDATE catalog_menuschedule SET available=TRUE WHERE tenant_id=? AND id=?', [$this->id(), $row['id']]);
                else $this->db->rows('INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,\'date\',?,NULL,TRUE,NULL,0,NULL)', [$this->id(), $id, $slotId, $date]);
            }
        });
    }
    public function setDayAvailability(string $date,int $slotId,int $itemId,bool $available,int $revision):void {
        self::date($date);$this->slot($slotId);$item=$this->item($itemId);
        if($date<date('Y-m-d')||$item['fulfilment']!=='scheduled')throw new HttpError(422,'Choose a current meal date and scheduled dish.');
        $this->db->transaction(function()use($date,$slotId,$itemId,$available,$revision){
            $this->lock();if($revision!==$this->menuRevision($date,$slotId))throw new HttpError(409,'This menu changed. Reload before saving.');
            $this->materializeMenu($date,$slotId);
            $this->db->rows('INSERT INTO catalog_menuday(tenant_id,slot_id,on_date,revision,updated_at) VALUES(?,?,?,1,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id,slot_id,on_date) DO UPDATE SET revision=catalog_menuday.revision+1,updated_at=CURRENT_TIMESTAMP',[$this->id(),$slotId,$date]);
            $row=$this->db->one("SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND slot_id=? AND item_id=? AND mode='date' AND on_date=?",[$this->id(),$slotId,$itemId,$date]);
            if($row)$this->db->rows('UPDATE catalog_menuschedule SET available=? WHERE tenant_id=? AND id=?',[$available,$this->id(),$row['id']]);
            else $this->db->rows("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,?,NULL,0,NULL)",[$this->id(),$itemId,$slotId,$date,$available]);
        });
    }
    public function family(int $id):array {
        $children=[];foreach($this->categories() as $category)if($category['active'])$children[$category['parent_id']][]=(int)$category['id'];
        $seen=[$id=>true];$todo=[$id];while($todo){$parent=array_pop($todo);foreach($children[$parent]??[] as $child)if(!isset($seen[$child])){$seen[$child]=true;$todo[]=$child;}}
        return array_keys($seen);
    }
    public function zoneQuote(string $pincode,string $slotKey,int $subtotal,?int $areaId=null):array {
        return (new Delivery($this))->local($pincode,[$slotKey],$subtotal,$areaId);
    }
}
