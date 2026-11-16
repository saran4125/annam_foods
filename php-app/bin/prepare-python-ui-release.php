<?php
declare(strict_types=1);
// Build-time only: never points at an installed store's database.
if(PHP_SAPI!=='cli')exit(1);
require dirname(__DIR__).'/src/bootstrap.php';
$file=ANNAM_ROOT.'/build/local/annam.sqlite';
$db=new PDO('sqlite:'.$file,null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
foreach(['auth_user','orders_customer','orders_order','tenancy_tenantsecrets','payments_razorpayconnection'] as $table){if($db->query('SELECT COUNT(*) FROM '.$table)->fetchColumn())throw new RuntimeException('Release input must contain public catalog data only.');}
$data=json_decode(file_get_contents(ANNAM_ROOT.'/resources/breakfast-review.json'),true,512,JSON_THROW_ON_ERROR);
$stmt=$db->prepare('SELECT id FROM tenancy_tenant WHERE slug=?');$stmt->execute([$data['tenant_slug']]);$tenant=(int)$stmt->fetchColumn();if(!$tenant)throw new RuntimeException('The reference store is missing.');
$db->beginTransaction();
$categories=$db->query('SELECT * FROM catalog_menucategory WHERE tenant_id='.(int)$tenant)->fetchAll(PDO::FETCH_ASSOC);
foreach($categories as $source){
 if(!preg_match('/^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*[-–:]?\s*(Breakfast|Lunch|Dinner|Snacks)$/i',trim($source['name']),$m))continue;
 $name=ucfirst(strtolower($m[2]));$slug=strtolower($name);$q=$db->prepare('SELECT id FROM catalog_menucategory WHERE tenant_id=? AND slug=?');$q->execute([$tenant,$slug]);$target=$q->fetchColumn();
 if(!$target){$q=$db->prepare('INSERT INTO catalog_menucategory(name,slug,description,image,parent_id,sort,active,tenant_id) VALUES(?,?,?,?,?,?,?,?)');$q->execute([$name,$slug,$source['description'],$source['image'],null,$source['sort'],1,$tenant]);$target=$db->lastInsertId();}
 $db->prepare("UPDATE catalog_menuitem SET category_id=? WHERE tenant_id=? AND category_id=? AND fulfilment='scheduled'")->execute([$target,$tenant,$source['id']]);
 $q=$db->prepare('SELECT COUNT(*) FROM catalog_menuitem WHERE tenant_id=? AND category_id=?');$q->execute([$tenant,$source['id']]);$items=(int)$q->fetchColumn();$q=$db->prepare('SELECT COUNT(*) FROM catalog_menucategory WHERE tenant_id=? AND parent_id=?');$q->execute([$tenant,$source['id']]);if(!$items&&!$q->fetchColumn())$db->prepare('UPDATE catalog_menucategory SET active=0 WHERE tenant_id=? AND id=?')->execute([$tenant,$source['id']]);
}
$q=$db->prepare("SELECT id FROM catalog_menucategory WHERE tenant_id=? AND slug='breakfast'");$q->execute([$tenant]);$category=(int)$q->fetchColumn();if(!$category)throw new RuntimeException('Breakfast category was not prepared.');
foreach($data['items'] as $r){
 $q=$db->prepare('SELECT id FROM catalog_menuitem WHERE tenant_id=? AND retailer_id=?');$q->execute([$tenant,$r['retailer_id']]);$id=$q->fetchColumn();
 if($id)$db->prepare('UPDATE catalog_menuitem SET name=?,price=?,in_stock=?,active=1,category_id=? WHERE tenant_id=? AND id=?')->execute([$r['name'],$r['price'],$r['in_stock']?1:0,$category,$tenant,$id]);
 else $db->prepare("INSERT INTO catalog_menuitem(name,description,price,image,is_veg,tags,active,sort,category_id,tenant_id,fulfilment,retailer_id,sac,tax_rate,admin_notes,in_stock,weight) VALUES(?,'',?,?,1,'[]',1,0,?,?,'scheduled',?,'',NULL,'',?,'')")->execute([$r['name'],$r['price'],$r['image'],$category,$tenant,$r['retailer_id'],$r['in_stock']?1:0]);
}
$q=$db->prepare('SELECT features,theme FROM tenancy_tenantconfig WHERE tenant_id=?');$q->execute([$tenant]);$config=$q->fetch(PDO::FETCH_ASSOC);$features=json_decode($config['features'],true);$features['carry_forward_meals']=true;$theme=json_decode($config['theme'],true);$theme['hero_product_ids']=['KEI1','MRP1','PP2','PT4'];$q=$db->prepare('UPDATE tenancy_tenantconfig SET features=?,theme=? WHERE tenant_id=?');$q->execute([json_encode($features,JSON_THROW_ON_ERROR),json_encode($theme,JSON_THROW_ON_ERROR),$tenant]);
// This build contains no operational records. Publish only the reviewed starting
// breakfast from the Python manifest; subsequent unsaved dates use carry-forward.
$plan=json_decode(file_get_contents(ANNAM_ROOT.'/resources/breakfast-menu.json'),true,512,JSON_THROW_ON_ERROR);
if($plan['tenant_slug']!==$data['tenant_slug'])throw new RuntimeException('Menu and catalog stores differ.');
$q=$db->prepare('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?');$q->execute([$tenant,$plan['slot']]);$slot=(int)$q->fetchColumn();if(!$slot)throw new RuntimeException('Reviewed meal slot is missing.');
$q=$db->prepare('SELECT id FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?');$q->execute([$tenant,$slot,$plan['date']]);
if(!$q->fetchColumn()){
 $q=$db->prepare('INSERT INTO catalog_menuday(tenant_id,slot_id,on_date,revision,updated_at) VALUES(?,?,?,1,?)');$q->execute([$tenant,$slot,$plan['date'],gmdate('Y-m-d H:i:s')]);
 foreach($data['items'] as $r){
  $q=$db->prepare("SELECT id FROM catalog_menuitem WHERE tenant_id=? AND retailer_id=? AND fulfilment='scheduled'");$q->execute([$tenant,$r['retailer_id']]);$item=(int)$q->fetchColumn();if(!$item)throw new RuntimeException('Reviewed breakfast product is missing.');
  $q=$db->prepare("SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND slot_id=? AND item_id=? AND mode='date' AND on_date=?");$q->execute([$tenant,$slot,$item,$plan['date']]);
  if(!$q->fetchColumn())$db->prepare("INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,'date',?,NULL,1,NULL,0,NULL)")->execute([$tenant,$item,$slot,$plan['date']]);
 }
}
$db->commit();if($db->query('PRAGMA integrity_check')->fetchColumn()!=='ok'||$db->query('PRAGMA foreign_key_check')->fetch())throw new RuntimeException('Release database integrity failed.');
$path=ANNAM_ROOT.'/build/local/DATA-INCLUDED.json';$report=json_decode(file_get_contents($path),true);$report['counts']['catalog_menuitem']=(int)$db->query('SELECT COUNT(*) FROM catalog_menuitem')->fetchColumn();$report['counts']['catalog_menucategory']=(int)$db->query('SELECT COUNT(*) FROM catalog_menucategory')->fetchColumn();$report['python_ui_reference']='6b626cb';$report['breakfast_review']=$data['source'];$report['menus']='Original historical dates preserved. Ten reviewed breakfast dishes scheduled from 2026-11-16. Latest saved breakfast, lunch and dinner continue until staff save a changed or empty menu.';$report['breakfast_menu']=$plan;$report['verification_scope']='Verified original public SQLite snapshot plus reviewed Python manifests at 6b626cb; not a direct export or full comparison of live Render PostgreSQL.';file_put_contents($path,json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));echo "Prepared plain meal categories and ten owner-reviewed breakfast products. Reviewed breakfast starting menu scheduled; breakfast, lunch and dinner continue until changed.\n";
