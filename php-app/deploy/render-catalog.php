<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit(1);
require dirname(__DIR__).'/src/bootstrap.php';
$previewRoot=getenv('PREVIEW_DATA_ROOT')?:'/tmp/annam-php-preview';
if(!in_array($previewRoot,['/tmp/annam-php-preview','/var/data/annam-php-preview'],true)||getenv('APP_ENV')!=='preview'||getenv('DATABASE_DSN')!=='sqlite:'.$previewRoot.'/annam.sqlite')throw new RuntimeException('Only the disposable preview may be seeded.');
// This provider-disabled disposable preview must have an explicit test route
// through checkout. Never expose manual fallback in normal production checkout.
if(getenv('PAYMENTS_ENABLED')!=='0'||getenv('MESSAGING_ENABLED')!=='0')throw new RuntimeException('Preview providers must remain disabled.');
$store=new Annam\Store(new Annam\Database());
$features=$store->config['features'];$features['checkout_test_mode']=true;
$store->db->rows('UPDATE tenancy_tenantconfig SET features=? WHERE tenant_id=?',[json_encode($features),$store->id()]);$store->reload();
$marker=$previewRoot.'/new-catalog';if(!is_file($marker))return;
$resources=new Annam\Resources($store);
(new Annam\CatalogSync($store))->run(true);
$store->db->transaction(function()use($store,$resources){
 $store->lock();$features=$store->config['features'];$features['carry_forward_meals']=true;$store->db->rows('UPDATE tenancy_tenantconfig SET features=? WHERE tenant_id=?',[json_encode($features),$store->id()]);
 $daily=json_decode(file_get_contents(ANNAM_ROOT.'/resources/catalog-sync.json'),true)['daily_menu'];
 $breakfast=json_decode(file_get_contents(ANNAM_ROOT.'/resources/breakfast-review.json'),true);
 $plan=json_decode(file_get_contents(ANNAM_ROOT.'/resources/breakfast-menu.json'),true);
 $menus=[['date'=>$daily['date'],'meal'=>'lunch','items'=>$daily['slots']['lunch']],['date'=>$daily['date'],'meal'=>'dinner','items'=>$daily['slots']['dinner']],['date'=>$plan['date'],'meal'=>'breakfast','items'=>$breakfast['items']]];
 foreach($menus as $menu){
  $slot=$store->db->one('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?',[$store->id(),$menu['meal']]);if(!$slot)throw new RuntimeException('Reviewed meal time is missing.');
  $category=$store->db->one('SELECT id FROM catalog_menucategory WHERE tenant_id=? AND slug=?',[$store->id(),$menu['meal']]);$categoryId=$category['id']??$resources->save('categories',null,['name'=>ucfirst($menu['meal']),'slug'=>$menu['meal'],'active'=>1]);
  $ids=[];
  foreach($menu['items'] as $row){
   $item=null;foreach($store->items('scheduled') as $candidate)if((isset($row['retailer_id'])&&$candidate['retailer_id']===$row['retailer_id'])||Annam\CatalogSync::normal($candidate['name'])===Annam\CatalogSync::normal($row['name'])){$item=$candidate;break;}
   $values=['name'=>$row['name'],'price'=>$row['price'],'fulfilment'=>'scheduled','category_id'=>$categoryId,'in_stock'=>$row['in_stock']??true,'active'=>1,'is_veg'=>1,'sort'=>0,'description'=>$item['description']??'','admin_notes'=>$item['admin_notes']??'','weight'=>$item['weight']??''];
   $id=$resources->save('dishes',$item?(int)$item['id']:null,$values);
   if(isset($row['retailer_id']))$store->db->rows('UPDATE catalog_menuitem SET retailer_id=? WHERE tenant_id=? AND id=?',[$row['retailer_id'],$store->id(),$id]);
   if(!empty($row['image']))$store->db->rows("UPDATE catalog_menuitem SET image=? WHERE tenant_id=? AND id=? AND image=''",[$row['image'],$store->id(),$id]);
   $ids[]=$id;
  }
  if(!$store->db->one('SELECT id FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?',[$store->id(),$slot['id'],$menu['date']])){
   // Fresh public seed import only: retain the actual reviewed historical dates.
   $store->db->rows('INSERT INTO catalog_menuday(tenant_id,slot_id,on_date,revision,updated_at) VALUES(?,?,?,1,CURRENT_TIMESTAMP)',[$store->id(),$slot['id'],$menu['date']]);
   foreach($ids as $id)$store->db->rows("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,TRUE,NULL,0,NULL)",[$store->id(),$id,$slot['id'],$menu['date']]);
  }
 }
 if(!$store->db->one("SELECT id FROM catalog_slot WHERE tenant_id=? AND key='snacks'",[$store->id()]))$resources->save('slots',null,['key'=>'snacks','label'=>'Snacks','order_cutoff'=>'23:59:00','order_opens_at'=>'00:00:00','order_days_before'=>1,'delivery_from'=>'09:00:00','delivery_to'=>'21:00:00','sort'=>3,'active'=>1]);
});
unlink($marker);echo "Reviewed public catalog and dated breakfast/lunch/dinner menus seeded. No live orders or customer history copied.\n";
