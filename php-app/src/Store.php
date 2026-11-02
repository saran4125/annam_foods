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
    public function slots(): array { return $this->db->rows('SELECT * FROM catalog_slot WHERE tenant_id=? AND active ORDER BY sort,key', [$this->id()]); }
    public function slot(int $id): array { return $this->db->one('SELECT * FROM catalog_slot WHERE tenant_id=? AND id=?', [$this->id(), $id]) ?? throw new HttpError(404, 'Meal not found.'); }
    public function items(string $kind = '', string $query = '', ?int $category = null): array {
        $sql = 'SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id WHERE i.tenant_id=?';
        $params = [$this->id()];
        if ($kind) { $sql .= ' AND i.fulfilment=?'; $params[] = $kind; }
        if ($query) { $sql .= ' AND i.name ILIKE ?'; $params[] = '%' . $query . '%'; }
        if ($category) { $ids=$this->family($category);$sql.=' AND i.category_id IN ('.implode(',',array_fill(0,count($ids),'?')).')';array_push($params,...$ids); }
        return $this->db->rows($sql . ' ORDER BY i.sort,i.name', $params);
    }
    public function pageItems(string $kind,string $query,?int $category,int $page,int $size=30,array $filters=[],string $meal=''):array {
        $size=max(1,min($size,100));$params=[$this->id()];$where=' WHERE i.tenant_id=?';if($kind){$where.=' AND i.fulfilment=?';$params[]=$kind;}if($query){$where.=' AND i.name ILIKE ?';$params[]='%'.mb_substr($query,0,120).'%';}
        if($category){$family=$this->family($category);$where.=' AND i.category_id IN ('.implode(',',array_fill(0,count($family),'?')).')';array_push($params,...$family);}
        foreach(['active','in_stock'] as $field)if(array_key_exists($field,$filters)){$where.=' AND i.'.$field.'=?';$params[]=(bool)$filters[$field];}
        if($meal){$where.=$meal==='unassigned'?' AND NOT EXISTS':' AND EXISTS';$where.='(SELECT 1 FROM catalog_menuschedule m JOIN catalog_slot s ON s.id=m.slot_id AND s.tenant_id=m.tenant_id WHERE m.tenant_id=i.tenant_id AND m.item_id=i.id';if($meal!=='unassigned'){$where.=' AND s.key=?';$params[]=$meal;}$where.=')';}
        $total=(int)$this->db->one('SELECT COUNT(*) AS n FROM catalog_menuitem i'.$where,$params)['n'];$page=max(1,min($page,max(1,(int)ceil($total/$size))));$records=$this->db->rows('SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id'.$where.' ORDER BY i.sort,i.name,i.id LIMIT '.$size.' OFFSET '.(($page-1)*$size),$params);return compact('records','total','page');
    }
    public function item(int $id): array {
        return $this->db->one('SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id WHERE i.tenant_id=? AND i.id=?', [$this->id(), $id]) ?? throw new HttpError(404, 'Dish not found.');
    }
    public function categories(): array { return $this->db->rows('SELECT * FROM catalog_menucategory WHERE tenant_id=? ORDER BY sort,name', [$this->id()]); }
    public function pages(): array { return $this->db->rows('SELECT * FROM content_page WHERE tenant_id=? AND published ORDER BY sort,title', [$this->id()]); }
    public function logo(): string { return image_url($this->config['theme']['logo_url'] ?? '') ?: '/media/brand/annam-logo.png'; }
    public static function date(string $value): string {
        $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        if (!$date || $date->format('Y-m-d') !== $value) throw new HttpError(422, 'Choose a valid menu date.');
        return $value;
    }
    public function menu(string $date, int $slotId, bool $includeUnavailable = false): array {
        self::date($date); $this->slot($slotId);
        $day = $this->db->one('SELECT * FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?', [$this->id(), $slotId, $date]);
        $params = [$this->id(), $slotId, $date];
        $condition = '(s.mode=\'date\' AND s.on_date=?)';
        if (!$day) { $condition .= ' OR (s.mode=\'weekday\' AND s.weekday=?)'; $params[] = (int)(new \DateTimeImmutable($date))->format('N') - 1; }
        $rows = $this->db->rows('SELECT i.*,s.id AS schedule_id,s.mode,s.available,s.qty_limit,s.qty_sold,COALESCE(s.price_override,i.price) AS effective_price FROM catalog_menuschedule s JOIN catalog_menuitem i ON i.id=s.item_id AND i.tenant_id=s.tenant_id WHERE s.tenant_id=? AND s.slot_id=? AND (' . $condition . ') AND i.fulfilment=\'scheduled\' ORDER BY CASE WHEN s.mode=\'date\' THEN 1 ELSE 0 END', $params);
        $chosen = [];
        foreach ($rows as $row) $chosen[(int)$row['id']] = $row;
        $result = array_filter(array_values($chosen), fn($r) => $r['active'] && ($includeUnavailable || ($r['available'] && ($r['in_stock']??true) && ($r['qty_limit'] === null || $r['qty_sold'] < $r['qty_limit']))));
        usort($result, fn($a, $b) => [$a['sort'], $a['name']] <=> [$b['sort'], $b['name']]);
        return array_values($result);
    }
    public function menuRevision(string $date, int $slotId): int {
        $row = $this->db->one('SELECT revision FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?', [$this->id(), $slotId, self::date($date)]);
        return (int)($row['revision'] ?? 0);
    }
    public function saveMenu(string $date, int $slotId, array $ids, int $revision): void {
        self::date($date); $this->slot($slotId);
        if ($date < date('Y-m-d')) throw new HttpError(422, 'Historical menus cannot be changed.');
        $ids = array_values(array_unique(array_map('intval', $ids)));
        if (count($ids) > 500) throw new HttpError(422, 'Too many selected dishes.');
        $this->db->transaction(function () use ($date, $slotId, $ids, $revision): void {
            // Serialize full-menu saves against the same store, including the first save.
            $this->db->one('SELECT id FROM tenancy_tenant WHERE id=? FOR UPDATE', [$this->id()]);
            if ($revision !== $this->menuRevision($date, $slotId)) throw new HttpError(409, 'This menu changed in another window. Reload it before saving.');
            foreach ($ids as $id) {
                $item = $this->item($id);
                if ($item['fulfilment'] !== 'scheduled' || !$item['active']) throw new HttpError(422, 'Choose active meal dishes only.');
            }
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
            $saved=$this->db->one('SELECT id FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?',[$this->id(),$slotId,$date]);
            if(!$saved){
                // Copy effective inherited rows before saving the first full dated menu.
                $rows=$this->db->rows("SELECT * FROM catalog_menuschedule WHERE tenant_id=? AND slot_id=? AND ((mode='date' AND on_date=?) OR (mode='weekday' AND weekday=?)) ORDER BY CASE WHEN mode='date' THEN 1 ELSE 0 END",[$this->id(),$slotId,$date,(int)(new \DateTimeImmutable($date))->format('N')-1]);$effective=[];foreach($rows as $r)$effective[$r['item_id']]=$r;
                foreach($effective as $r)if($r['mode']!=='date')$this->db->rows("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,?,?,?,?)",[$this->id(),$r['item_id'],$slotId,$date,$r['available'],$r['qty_limit'],$r['qty_sold'],$r['price_override']]);
            }
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
