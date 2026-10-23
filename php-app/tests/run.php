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
        $template['features']=json_encode(['snacks_courier'=>true,'website_ordering'=>true,'manual_payments'=>true]);$template['theme']='{}';$template['checkout_settings']='{}';$template['storefront_design']='{}';$template['home_sections']='[]';
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
    $profileTemplate=$db->one('SELECT * FROM tenancy_billingprofile ORDER BY id LIMIT 1');unset($profileTemplate['id']);$profileTemplate['tenant_id']=$tenant;$profileTemplate['legal_name']='Test kitchen';$profileTemplate['address']='Test address';$profileTemplate['state']='Tamil Nadu';$profileTemplate['state_code']='33';$profileTemplate['fssai_no']='12345678901234';$profileTemplate['gst_mode']='unregistered';$profileTemplate['tax_rate']='0.00';$profileTemplate['round_total']=false;$profileTemplate['invoice_prefix']='PT';$profileTemplate['number_format']='{prefix}/{fy}/{seq:05d}';$profileTemplate['bill_timing']='on_payment';insert($db,'tenancy_billingprofile',$profileTemplate);
    $resources->toggle('dishes',$item);$_SESSION=[];
    $details=['name'=>'PHP test customer','phone'=>'919999999999','email'=>'','line1'=>'Test street','line2'=>'','landmark'=>'','city'=>'Chennai','pincode'=>'600011','zone_id'=>null,'payment_method'=>'manual'];
    $orders=new Annam\Orders($store);$billing=new Annam\Billing($store);$payments=new Annam\Payments($store);$checkout=new Annam\Checkout($store);
    $db->rows('UPDATE catalog_menuschedule SET qty_limit=NULL,available=TRUE WHERE tenant_id=? AND item_id=? AND on_date=?',[$tenant,$item,$tomorrow]);
    $db->rows('UPDATE catalog_menuitem SET price=? WHERE tenant_id=? AND id=?',['350.00',$tenant,$item]);
    $db->rows('UPDATE tenancy_tenantconfig SET features=? WHERE tenant_id=?',[json_encode(['website_ordering'=>true,'manual_payments'=>true,'snacks_courier'=>true]),$tenant]);$store->reload();
    test('checkout refuses unserved pincodes and area minimum bypasses',function()use($store,$checkout,$details,$tomorrow,$slot,$item){
        Cart::add($store,['item_id'=>$item,'quantity'=>1,'date'=>$tomorrow,'slot_id'=>$slot]);$bad=$details;$bad['pincode']='699999';expectError(fn()=>$checkout->review($bad),422);
        $bad=$details;$bad['zone_id']=999999;expectError(fn()=>$checkout->review($bad),422);
    });
    $review=$checkout->review($details);$placed=$checkout->place($review['reference']);
    test('duplicate checkout submission returns one order after the cart is cleared',function()use($checkout,$review,$placed,$db,$tenant){$again=$checkout->place($review['reference']);check($again['id']===$placed['id'],'Duplicate order');check(!isset($_SESSION['cart']),'Cart not cleared');check((int)$db->one('SELECT count(*) AS n FROM orders_order WHERE tenant_id=?',[$tenant])['n']===1,'Unexpected order count');});
    test('guest receipts require the originating browser',function()use($checkout,$review,$placed){check($checkout->guest($review['reference'])['id']===$placed['id'],'Receipt missing');$browser=$_SESSION['checkout_browser'];unset($_SESSION['checkout_browser']);expectError(fn()=>$checkout->guest($review['reference']),404);$_SESSION['checkout_browser']=$browser;});
    test('order snapshots survive catalog edits',function()use($db,$tenant,$item,$orders,$placed){$db->rows('UPDATE catalog_menuitem SET price=? WHERE tenant_id=? AND id=?',['777.77',$tenant,$item]);check($orders->get($placed['id'])['total']===$placed['total'],'Snapshot changed');});
    test('unpaid bills cannot consume invoice numbers',function()use($billing,$placed,$db,$tenant){expectError(fn()=>$billing->issue($placed['id']),422);check((int)$db->one('SELECT count(*) AS n FROM billing_invoicesequence WHERE tenant_id=?',[$tenant])['n']===0,'Number consumed');});
    $orders->confirm($placed['id'],'tester','cash-received',true);$invoice=$billing->issue($placed['id']);
    test('paid bill issuance is idempotent and immutable',function()use($billing,$placed,$invoice,$store){check($billing->issue($placed['id'])['id']===$invoice['id'],'Duplicate bill');check($invoice['total']===$placed['total'],'Wrong bill total');check($invoice['buyer']['delivery_address']['line1']==='Test street','Address missing');try{$store->update('billing_invoice',$invoice['id'],['total'=>'1.00']);throw new RuntimeException('Bill mutable');}catch(LogicException){} });
    test('fulfilment cannot skip steps or reopen terminal orders',function()use($orders,$placed){expectError(fn()=>$orders->advance($placed['id'],'delivered','tester'),422);foreach(['confirmed','preparing','out_for_delivery','delivered'] as $state)$orders->advance($placed['id'],$state,'tester');expectError(fn()=>$orders->advance($placed['id'],'cancelled','tester'),422);});
    test('credits cannot exceed the original paid amount cumulatively',function()use($billing,$invoice){$amount=Money::parse($invoice['total']);$credit=$billing->credit($invoice['id'],$amount,'Customer refund');check($credit['total']===$invoice['total'],'Credit amount');expectError(fn()=>$billing->credit($invoice['id'],1,'Duplicate'),422);});
    test('tax arithmetic uses exact half-up paise for inclusive and exclusive rates',function(){check(Money::tax(10500,500,true)===['base'=>10000,'tax'=>500],'Inclusive tax');check(Money::tax(10010,500,false)['tax']===501,'Half-up tax');check(Annam\Billing::words(98000)==='Nine Hundred Eighty Rupees Only','Amount words');});
    putenv('SECRETS_KEY='.strtr(base64_encode(str_repeat('K',32)),'+/','-_'));
    test('encrypted credentials round-trip and tampering is refused',function(){ $token=Annam\Crypto::encrypt('private-test-token');check(Annam\Crypto::decrypt($token)==='private-test-token','Secret failed');$raw=base64_decode(strtr($token,'-_','+/'));$raw[30]=chr(ord($raw[30])^1);expectError(fn()=>Annam\Crypto::decrypt(strtr(base64_encode($raw),'+/','-_')),503);});
    $connection=$store->insert('payments_razorpayconnection',['mode'=>'test','enabled'=>true,'key_id'=>'rzp_test_fixture','_key_secret'=>Annam\Crypto::encrypt('fixture-secret'),'_webhook_secret'=>Annam\Crypto::encrypt('fixture-webhook-secret'),'updated_at'=>date('c')]);
    $quote=Annam\Pricing::totals([Annam\Pricing::line($store->item($shop),1)],0,$store->profile())+['kind'=>'courier','zone'=>[],'slot'=>null,'date'=>null];$online=$details;$online['payment_method']='online';$paidOrder=$orders->create($quote,$online,'test-online-payment');$intent=$payments->intent($paidOrder,$connection);
    $calls=[];Annam\Http::$transport=function($method,$url,$headers,$body)use(&$calls,$intent){$calls[]=$method.' '.$url;if($method==='POST'&&str_ends_with($url,'/orders'))return ['id'=>'order_fixture','amount'=>(int)$intent['amount'],'currency'=>'INR','receipt'=>'sk_'.str_replace('-','',$intent['id'])];if(str_ends_with($url,'/payments/pay_fixture'))return ['id'=>'pay_fixture','order_id'=>'order_fixture','amount'=>(int)$intent['amount'],'currency'=>'INR','status'=>'captured','captured'=>true];return ['items'=>[]];};
    test('Razorpay order creation retries reuse the original provider order',function()use($payments,$paidOrder,&$calls){$first=$payments->start($paidOrder['id']);$second=$payments->start($paidOrder['id']);check($first['provider_order_id']===$second['provider_order_id'],'Provider order changed');check(count($calls)===1,'Duplicate provider create');});
    test('browser signatures and provider amounts are both required before payment is marked paid',function()use($payments,$paidOrder,$intent,$orders){expectError(fn()=>$payments->verify($paidOrder['id'],['razorpay_payment_id'=>'pay_fixture','razorpay_order_id'=>'order_fixture','razorpay_signature'=>'bad']),403);$bad=['id'=>'pay_fixture','order_id'=>'order_fixture','amount'=>1,'currency'=>'INR','status'=>'captured','captured'=>true];expectError(fn()=>$payments->apply($intent['id'],$bad),422);check($orders->get($paidOrder['id'])['payment_status']==='pending','Invalid payment applied');$payments->verify($paidOrder['id'],['razorpay_payment_id'=>'pay_fixture','razorpay_order_id'=>'order_fixture','razorpay_signature'=>hash_hmac('sha256','order_fixture|pay_fixture','fixture-secret')]);check($orders->get($paidOrder['id'])['payment_status']==='paid','Verified payment missing');});
    test('test captures do not issue real bills and cannot be manually confirmed',function()use($billing,$paidOrder,$orders){expectError(fn()=>$billing->issue($paidOrder['id']),422);expectError(fn()=>$orders->confirm($paidOrder['id'],'tester','manual',true),422);});
    test('failed payment events do not downgrade a captured payment',function()use($payments,$intent,$orders,$paidOrder){$payments->apply($intent['id'],['id'=>'pay_failed','order_id'=>'order_fixture','amount'=>(int)$intent['amount'],'currency'=>'INR','status'=>'failed']);check($orders->get($paidOrder['id'])['payment_status']==='paid','Paid status lost');});
    test('credentials and order records cannot cross store boundaries',function()use($otherStore,$connection,$intent,$placed,$invoice){foreach([['payments_razorpayconnection',$connection['id']],['payments_paymentintent',$intent['id']],['orders_order',$placed['id']],['billing_invoice',$invoice['id']]] as [$table,$id])expectError(fn()=>$otherStore->row($table,$id),404);});
    test('uncertain provider creation is reconciled instead of submitted twice',function()use($payments,$orders,$quote,$online,$connection){$order=$orders->create($quote,$online,'test-uncertain');$intent=$payments->intent($order,$connection);$posts=0;$gets=0;Annam\Http::$transport=function($method,$url,$headers,$body)use(&$posts,&$gets,$intent){if($method==='POST'){$posts++;throw new Annam\ProviderError(true);}$gets++;return ['items'=>[]];};try{$payments->start($order['id']);}catch(Annam\ProviderError){}try{$payments->start($order['id']);}catch(Annam\ProviderError){}check($posts===1&&$gets===1,'Uncertain creation was duplicated');});
    $secretTemplate=Annam\Messaging::defaults();$secretTemplate['tenant_id']=$tenant;$secretTemplate['wa_provider']='console';$secretTemplate['wa_phone_number_id']='123456789';$secretTemplate['wa_waba_id']='987654321';$secretTemplate['wa_verify_token']='fixture-verify-token';$secretTemplate['wa_app_secret_enc']=Annam\Crypto::encrypt('fixture-app-secret');$secretTemplate['wa_sync_token_enc']=Annam\Crypto::encrypt('fixture-sync-token');$secretTemplate['n8n_receive_url']='';insert($db,'tenancy_tenantsecrets',$secretTemplate);
    $messaging=new Annam\Messaging($store);$meta=['object'=>'whatsapp_business_account','entry'=>[['id'=>'987654321','changes'=>[['field'=>'messages','value'=>['metadata'=>['phone_number_id'=>'123456789'],'contacts'=>[['wa_id'=>'919999999999','profile'=>['name'=>'Test customer']]],'messages'=>[['from'=>'919999999999','id'=>'wamid.fixture.in','timestamp'=>(string)time(),'type'=>'text','text'=>['body'=>'Hello kitchen']]]]]]]]];
    test('Meta signatures and configured phone IDs protect the inbox',function()use($messaging,$meta,$db,$tenant){$raw=json_encode($meta);expectError(fn()=>$messaging->webhook($raw,'sha256=invalid'),403);$wrong=$meta;$wrong['entry'][0]['changes'][0]['value']['metadata']['phone_number_id']='000';$wrong=json_encode($wrong);$messaging->webhook($wrong,'sha256='.hash_hmac('sha256',$wrong,'fixture-app-secret'));check((int)$db->one('SELECT count(*) AS n FROM messaging_whatsappmessage WHERE tenant_id=?',[$tenant])['n']===0,'Foreign account imported');$messaging->webhook($raw,'sha256='.hash_hmac('sha256',$raw,'fixture-app-secret'));$messaging->webhook($raw,'sha256='.hash_hmac('sha256',$raw,'fixture-app-secret'));check((int)$db->one('SELECT count(*) AS n FROM messaging_whatsappmessage WHERE tenant_id=?',[$tenant])['n']===1,'Duplicate incoming message');});
    test('queued replies are idempotent and appear in the conversation',function()use($messaging,$db,$tenant){$conversation=$db->one('SELECT * FROM messaging_whatsappconversation WHERE tenant_id=?',[$tenant]);$token=bin2hex(random_bytes(16));$_SESSION['reply_tokens'][$token]=time();$messaging->reply($conversation['id'],'Thanks for ordering',$token,'tester');$messaging->reply($conversation['id'],'Thanks for ordering',$token,'tester');check((int)$db->one('SELECT count(*) AS n FROM messaging_outboundmessage WHERE tenant_id=?',[$tenant])['n']===1,'Duplicate reply queued');check((int)$db->one("SELECT count(*) AS n FROM messaging_whatsappmessage WHERE tenant_id=? AND direction='out'",[$tenant])['n']===1,'Reply mirror missing');});
    test('closed reply windows reject free-text sends',function()use($messaging,$db,$tenant){$conversation=$db->one('SELECT * FROM messaging_whatsappconversation WHERE tenant_id=?',[$tenant]);$db->rows("UPDATE messaging_whatsappconversation SET last_inbound_at=CURRENT_TIMESTAMP-INTERVAL '25 hours' WHERE tenant_id=?",[$tenant]);$token=bin2hex(random_bytes(16));$_SESSION['reply_tokens'][$token]=time();expectError(fn()=>$messaging->reply($conversation['id'],'Too late',$token,'tester'),422);});
    test('WhatsApp payload limits are enforced before queue insertion',function()use($messaging){expectError(fn()=>$messaging->queue('919999999999',['kind'=>'text','body'=>str_repeat('x',1025)]),422);expectError(fn()=>$messaging->queue('919999999999',['kind'=>'buttons','body'=>'Choose','buttons'=>array_fill(0,4,['id'=>'x','title'=>'Choice'])]),422);expectError(fn()=>$messaging->queue('919999999999',['kind'=>'cta_url','body'=>'Choose','label'=>'Link','url'=>'javascript:alert(1)']),422);});
    test('n8n sync requires its independent bearer token',function()use($messaging,$meta){$raw=json_encode(['event'=>'meta','payload'=>$meta]);expectError(fn()=>$messaging->sync($raw,'Bearer invalid'),403);$messaging->sync($raw,'Bearer fixture-sync-token');});
    test('Markdown preserves headings and neutralizes scripts and executable links',function(){$html=Annam\Markdown::render("# Policy\n\n**Fresh food**\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))");check(str_contains($html,'<h1>Policy</h1>')&&str_contains($html,'<strong>Fresh food</strong>'),'Formatting lost');check(!str_contains($html,'<script>')&&!str_contains($html,'href="javascript:'),'Executable content emitted');});
    test('media paths reject traversal and executable files',function(){foreach(['../.env','/etc/passwd','menu/evil.php','menu/%2e%2e/secret.png','menu/x.png?x'] as $path)check(Annam\Media::relative($path)===null,'Unsafe path accepted');});
    test('legacy Django guest sessions and encryption remain wire compatible',function(){
        $fixtures=json_decode(file_get_contents(__DIR__.'/compatibility.json'),true,64,JSON_THROW_ON_ERROR);check(Annam\Crypto::decrypt($fixtures['fernet'])==='legacy-secret-value','Django encrypted credential incompatible');$data=Annam\LegacySession::decode($fixtures['session'],'fixture-django-secret');check(($data['checkout.browser.1']??'')===str_repeat('a',32),'Django guest session incompatible');check(Annam\LegacySession::decode($fixtures['session'],'wrong-secret')===null,'Wrong session key accepted');
    });
    test('worker sends once and merges an early n8n callback into the queued reply',function()use($db,$tenant,$store,$messaging){
        putenv('APP_ENV=preview');$db->rows("UPDATE messaging_whatsappconversation SET last_inbound_at=CURRENT_TIMESTAMP WHERE tenant_id=?",[$tenant]);$db->rows("UPDATE tenancy_tenantsecrets SET wa_provider='n8n',n8n_send_url='https://example.com/send' WHERE tenant_id=?",[$tenant]);
        Annam\Http::$transport=function($method,$url,$headers,$body)use($messaging){$event=['event'=>'outbound','phone_number_id'=>'123456789','message'=>$body['graph'],'message_id'=>'wamid.fixture.out','timestamp'=>(string)time()];$messaging->sync(json_encode($event),'Bearer fixture-sync-token');return ['message_id'=>'wamid.fixture.out'];};
        $db->rows("UPDATE messaging_outboundmessage SET next_attempt_at=CURRENT_TIMESTAMP-INTERVAL '1 minute' WHERE tenant_id=?",[$tenant]);
        $worker=new Annam\Worker($store);$result=$worker->dispatch();check($result['sent']===1,'Queued reply not sent');check($worker->dispatch()['sent']===0,'Sent twice');check((int)$db->one("SELECT count(*) AS n FROM messaging_whatsappmessage WHERE tenant_id=? AND provider_message_id='wamid.fixture.out'",[$tenant])['n']===1,'Early callback duplicated timeline');
    });
    test('out-of-order receipts preserve read status',function()use($messaging,$meta,$db,$tenant){$event=$meta;unset($event['entry'][0]['changes'][0]['value']['messages']);foreach(['read','sent','delivered','failed'] as $state){$event['entry'][0]['changes'][0]['value']['statuses']=[['id'=>'wamid.fixture.out','status'=>$state,'recipient_id'=>'919999999999','timestamp'=>(string)time()]];$messaging->ingest($event,false);}check($db->one("SELECT status FROM messaging_whatsappmessage WHERE tenant_id=? AND provider_message_id='wamid.fixture.out'",[$tenant])['status']==='read','Receipt status downgraded');});
    test('reviewed checkout is refused if prices change before submission',function()use($store,$db,$tenant,$item,$tomorrow,$slot,$checkout,$details){$_SESSION['cart']=['kind'=>'scheduled','date'=>$tomorrow,'slot_id'=>$slot,'lines'=>[$item=>1]];$review=$checkout->review($details);$db->rows('UPDATE catalog_menuitem SET price=? WHERE tenant_id=? AND id=?',['888.88',$tenant,$item]);expectError(fn()=>$checkout->place($review['reference']),409);});
    test('courier ordering requires explicit approved pins and cannot be enabled with an empty list',function()use($store,$checkout,$details,$shop){expectError(fn()=>Annam\Settings::validateCheckout(['courier_enabled'=>true,'courier_pincodes'=>[],'courier_fee'=>'0','courier_minimum'=>'0']),422);$cart=['kind'=>'courier','date'=>null,'slot_id'=>null,'lines'=>[$shop=>1]];expectError(fn()=>$checkout->quote($cart,$details),422);});
    test('live capture survives invalid billing settings and refunds create one credit only',function()use($store,$db,$tenant,$orders,$payments,$quote,$online,$billing){
        $connection=$store->insert('payments_razorpayconnection',['mode'=>'live','enabled'=>false,'key_id'=>'rzp_live_fixture','_key_secret'=>Annam\Crypto::encrypt('live-fixture-secret'),'_webhook_secret'=>Annam\Crypto::encrypt('live-fixture-webhook'),'updated_at'=>date('c')]);
        $order=$orders->create($quote,$online,'test-live-payment');$intent=$payments->intent($order,$connection);$captured=['id'=>'pay_livefixture','order_id'=>'order_livefixture','amount'=>(int)$intent['amount'],'currency'=>'INR','status'=>'captured','captured'=>true];$refundId='';
        Annam\Http::$transport=function($method,$url,$headers,$body)use($intent,$captured,&$refundId){if($method==='POST'&&str_ends_with($url,'/orders'))return ['id'=>'order_livefixture','amount'=>(int)$intent['amount'],'currency'=>'INR','receipt'=>'sk_'.str_replace('-','',$intent['id'])];if($method==='POST'&&str_ends_with($url,'/refund')){$refundId=$body['notes']['seer_refund'];return ['id'=>'rfnd_livefixture'];}if(str_contains($url,'/refunds?'))return ['items'=>[['id'=>'rfnd_livefixture','payment_id'=>'pay_livefixture','status'=>'processed','amount'=>(int)$intent['amount'],'notes'=>['seer_refund'=>$refundId]]]];if(str_ends_with($url,'/payments/pay_livefixture'))return $captured;if(str_ends_with($url,'/payments'))return ['items'=>[$captured]];return ['items'=>[]];};
        $payments->start($order['id']);$db->rows("UPDATE tenancy_billingprofile SET address='' WHERE tenant_id=?",[$tenant]);$payments->apply($intent['id'],$captured);check($orders->get($order['id'])['payment_status']==='paid','Billing error undid captured payment');check($payments->forOrder($order['id'])['bill_error']!=='','Missing billing issue marker');$db->rows("UPDATE tenancy_billingprofile SET address='Test address' WHERE tenant_id=?",[$tenant]);$invoice=$billing->issue($order['id']);
        $payments->refund($order['id'],'Customer requested cancellation','tester');check($orders->get($order['id'])['payment_status']==='refunded','Verified refund missing');$payments->reconcile($order['id']);check((int)$db->one('SELECT count(*) AS n FROM billing_invoice WHERE tenant_id=? AND original_id=?',[$tenant,$invoice['id']])['n']===1,'Duplicate credit note');
        $event=json_encode(['event'=>'refund.processed','payload'=>['refund'=>['entity'=>['payment_id'=>'pay_livefixture']]]]);$signature=hash_hmac('sha256',$event,'live-fixture-webhook');$payments->webhook('live',$event,$signature,'evt_fixture');$payments->webhook('live',$event,$signature,'evt_fixture');check((int)$db->one('SELECT count(*) AS n FROM payments_paymentevent WHERE tenant_id=? AND event_id=?',[$tenant,'evt_fixture'])['n']===1,'Webhook not deduplicated');
    });
    Annam\Http::$transport=null;
    echo "$passed behavioural tests passed. All fixture records rolled back.\n";
} finally { $pdo->rollBack(); }
