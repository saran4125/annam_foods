<?php
declare(strict_types=1);
require dirname(__DIR__).'/src/bootstrap.php';
use Annam\{Database,Store,Money};
if(PHP_SAPI!=='cli')exit(1);
$db=new Database();$store=new Store($db);
function verify(bool $condition,string $message):void {if(!$condition)throw new RuntimeException($message);}
verify($db->one('PRAGMA integrity_check')['integrity_check']==='ok','SQLite integrity failed.');
verify($db->rows('PRAGMA foreign_key_check')===[],'Foreign-key integrity failed.');
$review=json_decode(file_get_contents(ANNAM_ROOT.'/resources/breakfast-review.json'),true,512,JSON_THROW_ON_ERROR);
$plan=json_decode(file_get_contents(ANNAM_ROOT.'/resources/breakfast-menu.json'),true,512,JSON_THROW_ON_ERROR);
$slot=$db->one('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?',[$store->id(),$plan['slot']]);
$all=$store->menu($plan['date'],(int)$slot['id'],true);
verify(count($all)===count($review['items']),'Reviewed starting menu is incomplete.');
$byKey=[];foreach($all as $item)$byKey[$item['retailer_id']]=$item;
foreach($review['items'] as $row){
 $item=$byKey[$row['retailer_id']]??null;
 verify($item!==null&&$item['name']===$row['name'],'Reviewed dish is missing.');
 verify(Money::parse($item['price'])===Money::parse($row['price']),'Reviewed price differs.');
 verify((bool)$item['in_stock']===$row['in_stock'],'Reviewed stock differs.');
 verify($store->item((int)$item['id'])['category_name']==='Breakfast','Reviewed category differs.');
}

$next=(new DateTimeImmutable($plan['date']))->modify('+1 day')->format('Y-m-d');
verify(count($store->menu($plan['date'],(int)$slot['id']))===8,'Starting meal stock differs.');
verify(count($store->menu($next,(int)$slot['id']))===8,'Reviewed breakfast does not continue tomorrow.');
foreach(['auth_user','orders_customer','orders_order','tenancy_tenantsecrets','payments_razorpayconnection','messaging_outboundmessage'] as $table)verify((int)$db->one('SELECT COUNT(*) AS n FROM '.$table)['n']===0,'Private operational data was bundled.');
verify((int)$db->one('SELECT COUNT(*) AS n FROM catalog_menuitem WHERE tenant_id=?',[$store->id()])['n']===325,'Unexpected catalog count.');
verify((int)$db->one('SELECT COUNT(*) AS n FROM delivery_deliveryzone WHERE tenant_id=?',[$store->id()])['n']===64,'Unexpected delivery-area count.');
echo "PASS clean reviewed database: integrity, 325 products, 64 areas, ten breakfast choices, eight in stock, next-day continuation, plain categories and no accounts/orders/credentials\n";
