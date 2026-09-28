<?php
/** Integration tests against the disposable demonstration site, never Annam. */
if(!defined('WP_CLI')||!WP_CLI||get_current_blog_id()!==3)throw new RuntimeException('Use the demo site.');
global $checks,$failures,$created;
$checks=0;$failures=[];$created=[];
function expect_seer(bool $condition,string $sentence):void{global $checks,$failures;$checks++;if(!$condition)$failures[]=$sentence;}
function rejects_seer(callable $action,string $sentence):void{try{$action();expect_seer(false,$sentence);}catch(InvalidArgumentException|Automattic\WooCommerce\StoreApi\Exceptions\RouteException $e){expect_seer(true,$sentence);}}
global $wpdb;
$prefix=$wpdb->prefix;$slot=(int)$wpdb->get_var("SELECT id FROM {$prefix}seer_slots WHERE slot_key='lunch'");
$date=wp_date('Y-m-d');$weekday='w:'.wp_date('N');
$before=new DateTimeImmutable($date.' 09:00:00',wp_timezone());
$ctx=Seer_Kitchen::context(['date'=>$date,'slot'=>'lunch'],$before);
try{
    foreach(['meal'=>'scheduled_meal','goods'=>'packaged_goods']as$key=>$kind){
        $p=new WC_Product_Simple();$p->set_name('__seer_test_'.$key);$p->set_status('publish');$p->set_regular_price($key==='meal'?'120.00':'80.00');$p->update_meta_data('_seer_fulfilment',$kind);$p->save();$created[$key]=$p->get_id();
    }
    $meal=$created['meal'];$goods=$created['goods'];
    $wpdb->insert($prefix.'seer_schedules',['product_id'=>$meal,'slot_id'=>$slot,'schedule_key'=>$weekday,'available'=>1,'quantity_limit'=>4,'quantity_sold'=>1]);
    expect_seer(Seer_Kitchen::quote($meal,3,$ctx)==='120.00','Weekly menu uses server price and remaining capacity.');
    rejects_seer(fn()=>Seer_Kitchen::quote($meal,4,$ctx),'Quantity cannot exceed remaining meal capacity.');
    $wpdb->insert($prefix.'seer_schedules',['product_id'=>$meal,'slot_id'=>$slot,'schedule_key'=>$date,'available'=>1,'quantity_limit'=>2,'price_override'=>'135.50']);$override=$wpdb->insert_id;
    expect_seer(Seer_Kitchen::quote($meal,1,$ctx)==='135.50','Dated menu takes precedence and prices from server records.');
    $wpdb->update($prefix.'seer_schedules',['available'=>0],['id'=>$override]);
    rejects_seer(fn()=>Seer_Kitchen::quote($meal,1,$ctx),'A closed dated override disables an available weekly meal.');
    $wpdb->update($prefix.'seer_schedules',['available'=>1,'quantity_sold'=>2],['id'=>$override]);
    rejects_seer(fn()=>Seer_Kitchen::quote($meal,1,$ctx),'Sold-out dated meal cannot be added.');
    $wpdb->update($prefix.'seer_schedules',['quantity_sold'=>0],['id'=>$override]);
    rejects_seer(fn()=>Seer_Kitchen::context(['date'=>$date,'slot'=>'lunch'],new DateTimeImmutable($date.' 23:59:00',wp_timezone())),'Exact cutoff closes ordering.');
    rejects_seer(fn()=>Seer_Kitchen::context(['date'=>'2026-02-30','slot'=>'lunch'],$before),'Impossible dates are rejected.');
    rejects_seer(fn()=>Seer_Kitchen::context(['date'=>$date,'slot'=>'forged'],$before),'Unknown delivery windows are rejected.');
    rejects_seer(fn()=>Seer_Kitchen::date(wp_date('Y-m-d',time()-86400),$before),'Past dates are rejected.');
    rejects_seer(fn()=>Seer_Kitchen::money('10.999'),'Money rejects extra decimal places.');
    expect_seer(Seer_Kitchen::quote($goods,1,[])==='80.00','Packaged goods can be browsed and added independently of meals.');
    rejects_seer(fn()=>Seer_Kitchen::quote($meal,1,[]),'Meals require a delivery context.');
    rejects_seer(fn()=>Seer_Kitchen::zone('600005',99999,$slot),'A forged zone identifier is rejected.');
    rejects_seer(fn()=>Seer_Kitchen::zone('000005'),'Invalid pincodes are rejected.');
    $zone=Seer_Kitchen::zone('600-005',0,$slot)[0];expect_seer($zone['fee']==='20.00'&&$zone['minimum_order']==='150.00','Delivery fees and minimums come from the store zone.');
    WC()->initialize_session();WC()->initialize_cart();WC()->session->set('seer_context',$ctx);
    rejects_seer(fn()=>seer_cart_validate($goods,'1.5'),'Ordinary forms reject fractional quantity tampering.');
    rejects_seer(fn()=>seer_cart_validate($goods,-1),'Ordinary forms reject negative quantities.');
    try{do_action('woocommerce_store_api_validate_add_to_cart',wc_get_product($meal),['quantity'=>3]);expect_seer(false,'Store API enforces dated capacity.');}
    catch(Automattic\WooCommerce\StoreApi\Exceptions\RouteException $e){expect_seer($e->getErrorCode()==='seer_delivery','Store API uses the same kitchen validation.');}
    expect_seer((bool)WC()->cart->add_to_cart($meal,1),'A valid meal can be added.');
    expect_seer((bool)WC()->cart->add_to_cart($goods,1),'Packaged goods can accompany a meal.');
    WC()->session->set('seer_zone',$zone);WC()->cart->calculate_totals();
    expect_seer(number_format(WC()->cart->get_subtotal(),2,'.','')==='215.50','Mixed-cart totals use the dated price plus the server goods price.');
    expect_seer(number_format(WC()->cart->get_fee_total(),2,'.','')==='20.00','Delivery is charged once per mixed cart.');
    rejects_seer(fn()=>Seer_Kitchen::persist_context(['date'=>wp_date('Y-m-d',time()+86400),'slot'=>'lunch']),'A nonempty cart cannot switch delivery date.');
    foreach(WC()->cart->get_cart()as$line)$line['data']->set_price('0.01');WC()->cart->calculate_totals();
    expect_seer(number_format(WC()->cart->get_subtotal(),2,'.','')==='215.50','Tampered in-memory prices are repriced from server records.');
    $original=get_current_blog_id();switch_to_blog(2);
    expect_seer(count(seer_slots())===0,'Annam has no fabricated meal windows.');
    rejects_seer(fn()=>Seer_Kitchen::zone('600005'),'Demonstration delivery zones do not leak into Annam.');
    $other=wc_get_product($meal);expect_seer(!$other||$other->get_name()!=='__seer_test_meal','Product identifiers resolve within the current site.');
    $owner=get_user_by('login','annam-owner');wp_set_current_user($owner->ID);
    expect_seer(current_user_can('edit_theme_options')&&current_user_can('edit_products'),'Owners can edit their site and catalog.');
    expect_seer(!current_user_can('install_plugins')&&!current_user_can('manage_network'),'Owners cannot install software or administer the network.');
    restore_current_blog();
    expect_seer(!current_user_can('edit_theme_options')&&!current_user_can('upload_files'),'Annam owner cannot edit demo layouts or media.');
    $error=apply_filters('rest_authentication_errors',null);expect_seer(is_wp_error($error)&&$error->get_error_code()==='seer_wrong_store','Authenticated cross-store REST access fails closed.');
    wp_set_current_user(0);
    foreach(['/wc/store/v1/checkout','/wc/store/v1/batch','/wc/v3/orders','/wc/v3/batch']as$route){$r=new WP_REST_Request('POST',$route);$response=apply_filters('rest_pre_dispatch',null,rest_get_server(),$r);expect_seer(is_wp_error($response)&&$response->get_error_data()['status']===403,'Order writes are blocked on '.$route);}
    try{$o=new WC_Order();$id=$o->save();expect_seer(!$id&&!$o->get_id(),'Manual order creation is disabled.');}catch(RuntimeException $e){expect_seer(str_contains($e->getMessage(),'disabled'),'Manual order creation is disabled.');}
}finally{
    WC()->cart?->empty_cart();wp_set_current_user(0);
    foreach($created as$id){$wpdb->delete($prefix.'seer_schedules',['product_id'=>$id]);$p=wc_get_product($id);if($p)$p->delete(true);}
}
file_put_contents('/opt/seer/reports/behaviour-tests.json',wp_json_encode(['checks'=>$checks,'failures'=>$failures,'site'=>home_url('/')],JSON_PRETTY_PRINT));
if($failures)WP_CLI::error(implode("\n",$failures));WP_CLI::success($checks.' behavioural checks passed.');
