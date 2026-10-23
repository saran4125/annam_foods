<?php
declare(strict_types=1);
require dirname(__DIR__) . '/src/bootstrap.php';
use Annam\{Database,Store,Resources,Money,Cart,Security,HttpError};

if (PHP_SAPI !== 'cli') exit(1);
if (!preg_match('/dbname=[^;]*(?:preview|test)[^;]*(?:;|$)/i', getenv('DATABASE_DSN') ?: '')) {
    fwrite(STDERR, "Tests require a disposable database whose name includes preview or test.\n"); exit(1);
}
$pdo = new PDO(getenv('DATABASE_DSN'), getenv('DATABASE_USER'), getenv('DATABASE_PASSWORD'), [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$db = new Database($pdo);
$pdo->beginTransaction();
$passed = 0;
function check(bool $condition, string $message): void { if (!$condition) throw new RuntimeException($message); }
function expectError(callable $operation, int $status): void {
    try { $operation(); } catch (HttpError $error) { check($error->status===$status, 'Unexpected error status'); return; }
    throw new RuntimeException('Expected operation to fail');
}
function insert(Database $db, string $table, array $values): int {
    $row=$db->one('INSERT INTO '.$table.'('.implode(',',array_map(fn($k)=>'"'.$k.'"',array_keys($values))).') VALUES('.implode(',',array_fill(0,count($values),'?')).') RETURNING id',array_values($values));
    return (int)$row['id'];
}
function test(string $name, callable $run): void {
    global $passed; $run(); $passed++; echo "PASS $name\n";
}
try {
    $suffix=bin2hex(random_bytes(6));
    $tenant=insert($db,'tenancy_tenant',['slug'=>'php-test-'.$suffix,'name'=>'Test kitchen','primary_domain'=>'','status'=>'active','created_at'=>date('c')]);
    $other=insert($db,'tenancy_tenant',['slug'=>'other-'.$suffix,'name'=>'Other kitchen','primary_domain'=>'','status'=>'active','created_at'=>date('c')]);
    $template=$db->one('SELECT * FROM tenancy_tenantconfig ORDER BY id LIMIT 1');
    unset($template['id']);
    foreach ([$tenant,$other] as $id) {
        $template['tenant_id']=$id;
        foreach ($template as $key=>$value) if ($value===true||$value===false) $template[$key]=$value;
        $template['theme']='{}';$template['checkout_settings']='{}';$template['storefront_design']='{}';$template['home_sections']='[]';
        insert($db,'tenancy_tenantconfig',$template);
    }
    putenv('STORE_SLUG=php-test-'.$suffix); $store=new Store($db); $resources=new Resources($store);
    $slot=insert($db,'catalog_slot',['tenant_id'=>$tenant,'key'=>'lunch','label'=>'Lunch','order_cutoff'=>'23:59:59','delivery_from'=>null,'delivery_to'=>null,'sort'=>0,'active'=>true]);
    $otherSlot=insert($db,'catalog_slot',['tenant_id'=>$other,'key'=>'lunch','label'=>'Lunch','order_cutoff'=>'23:59:59','delivery_from'=>null,'delivery_to'=>null,'sort'=>0,'active'=>true]);
    $item=$resources->save('dishes',null,['name'=>'Test lunch','fulfilment'=>'scheduled','price'=>'110.25','active'=>'1','is_veg'=>'1','sort'=>'0']);
    $item2=$resources->save('dishes',null,['name'=>'Other lunch','fulfilment'=>'scheduled','price'=>'85.50','active'=>'1','is_veg'=>'1','sort'=>'0']);
    $shop=$resources->save('dishes',null,['name'=>'Test podi','fulfilment'=>'courier','price'=>'150.10','active'=>'1','is_veg'=>'1','sort'=>'0']);
    putenv('STORE_SLUG=other-'.$suffix);$otherStore=new Store($db);
    $otherItem=(new Resources($otherStore))->save('dishes',null,['name'=>'Private dish','fulfilment'=>'scheduled','price'=>'999','active'=>'1','sort'=>'0']);
    putenv('STORE_SLUG=php-test-'.$suffix);
    $tomorrow=date('Y-m-d',strtotime('+1 day'));$after=date('Y-m-d',strtotime('+2 days'));
    $weekday=(int)(new DateTimeImmutable($tomorrow))->format('N')-1;
    insert($db,'catalog_menuschedule',['tenant_id'=>$tenant,'item_id'=>$item,'slot_id'=>$slot,'mode'=>'weekday','on_date'=>null,'weekday'=>$weekday,'available'=>true,'qty_limit'=>20,'qty_sold'=>2,'price_override'=>'100.50']);

    test('decimal prices are exact and never rounded through floating point',function(){
        check(Money::parse('0.10')+Money::parse('0.20')===30,'Decimal addition');
        check(Money::decimal(11025)==='110.25','Decimal output');
        foreach (['-1','1.001','NaN','1e3'] as $bad) { try { Money::parse($bad); throw new RuntimeException('Bad amount accepted'); } catch (InvalidArgumentException $expected) {} }
    });
    test('Django PBKDF2 passwords remain compatible',function(){
        $hash='pbkdf2_sha256$1000$test-salt$'.base64_encode(hash_pbkdf2('sha256','valid-password','test-salt',1000,32,true));
        check(Security::verifyPassword('valid-password',$hash),'Django password failed');
        check(!Security::verifyPassword('invalid',$hash),'Invalid password accepted');
        check(Security::verifyPassword('valid',password_hash('valid',PASSWORD_DEFAULT)),'PHP password failed');
    });
    test('store scopes apply to items, edits and meal slots',function()use($store,$resources,$otherItem,$otherSlot){
        expectError(fn()=>$store->item($otherItem),404);
        expectError(fn()=>$store->slot($otherSlot),404);
        expectError(fn()=>$resources->toggle('dishes',$otherItem),404);
    });
    test('date validation rejects nonexistent calendar dates',function(){expectError(fn()=>Store::date('2026-02-31'),422);});
    test('weekly prices resolve before a date has been reviewed',function()use($store,$tomorrow,$slot){
        $menu=$store->menu($tomorrow,$slot);check(count($menu)===1&&$menu[0]['effective_price']==='100.50','Weekly fallback incorrect');
    });
    test('a saved empty menu suppresses the weekly fallback',function()use($store,$tomorrow,$slot){
        $store->saveMenu($tomorrow,$slot,[],0);check($store->menu($tomorrow,$slot)===[],'Weekly rows reappeared');
    });
    test('stale menu revisions are refused without changing the menu',function()use($store,$tomorrow,$slot,$item){
        expectError(fn()=>$store->saveMenu($tomorrow,$slot,[$item],0),409);check($store->menu($tomorrow,$slot)===[],'Conflict overwrote menu');
    });
    test('saving a day does not change another day or stock counters',function()use($store,$db,$tomorrow,$after,$slot,$item,$item2){
        $store->saveMenu($tomorrow,$slot,[$item],1);$store->saveMenu($after,$slot,[$item2],0);
        $db->rows('UPDATE catalog_menuschedule SET qty_sold=3,qty_limit=4 WHERE tenant_id=? AND item_id=? AND on_date=?',[$store->id(),$item,$tomorrow]);
        $store->saveMenu($tomorrow,$slot,[],2);$store->saveMenu($tomorrow,$slot,[$item],3);
        $entry=$store->menu($tomorrow,$slot)[0];check((int)$entry['qty_sold']===3,'Counter reset');
        check((int)$store->menu($after,$slot)[0]['id']===$item2,'Other date changed');
    });
    test('forged client prices are ignored and stock limits are checked',function()use($store,$tomorrow,$slot,$item){
        $_SESSION=[];Cart::add($store,['item_id'=>$item,'quantity'=>1,'date'=>$tomorrow,'slot_id'=>$slot,'price'=>'0.01']);
        check(Cart::quote($store)['subtotal']===11025,'Client price trusted');
        expectError(fn()=>Cart::add($store,['item_id'=>$item,'quantity'=>1,'date'=>$tomorrow,'slot_id'=>$slot]),422);
    });
    test('meal and courier carts cannot be mixed',function()use($store,$shop){expectError(fn()=>Cart::add($store,['item_id'=>$shop,'quantity'=>1]),422);});
    test('delivery minimum excludes the delivery charge',function()use($resources,$store){
        $resources->save('zones',null,['area_name'=>'Perambur','pincode'=>'600011','delivery_fee'=>'100','min_order'=>'320','slot_keys'=>['lunch'],'active'=>'1']);
        expectError(fn()=>$store->zoneQuote('600011','lunch',25000),422);
        $quote=$store->zoneQuote('600011','lunch',32000);check($quote['fee']===10000&&$quote['minimum']===32000,'Wrong fee or minimum');
        expectError(fn()=>$store->zoneQuote('600011','breakfast',100000),422);
        expectError(fn()=>$store->zoneQuote('699999','lunch',100000),422);
    });
    test('shared pincodes require the correct area and preserve different rates',function()use($resources,$store){
        $a=$resources->save('zones',null,['area_name'=>'Ashok Nagar','pincode'=>'600083','delivery_fee'=>'40','min_order'=>'100','slot_keys'=>['lunch'],'active'=>'1']);
        $b=$resources->save('zones',null,['area_name'=>'Jaffar Khan Pet','pincode'=>'600083','delivery_fee'=>'60','min_order'=>'100','slot_keys'=>['lunch'],'active'=>'1']);
        expectError(fn()=>$store->zoneQuote('600083','lunch',20000),422);
        check($store->zoneQuote('600083','lunch',20000,$a)['fee']===4000,'Area A rate');
        check($store->zoneQuote('600083','lunch',20000,$b)['fee']===6000,'Area B rate');
    });
    test('archiving a dish preserves the schedule record',function()use($resources,$db,$store,$item){
        $resources->removeFromSale('dishes',$item);check(!$store->item($item)['active'],'Not archived');
        check((int)$db->one('SELECT count(*) AS n FROM catalog_menuschedule WHERE tenant_id=? AND item_id=?',[$store->id(),$item])['n']>0,'History deleted');
    });
    test('archived dishes stay hidden even when unavailable menu entries are requested',function()use($store,$tomorrow,$slot,$item){
        check(!in_array($item,array_column($store->menu($tomorrow,$slot,true),'id')),'Archived dish exposed');
    });
    echo "$passed behavioural tests passed. All fixture records rolled back.\n";
} finally { $pdo->rollBack(); }
