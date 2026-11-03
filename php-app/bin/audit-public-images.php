<?php
declare(strict_types=1);
require dirname(__DIR__).'/src/bootstrap.php';
try {
    $db=new Annam\Database();$store=new Annam\Store($db);$report=['store'=>'annam','products'=>[],'categories'=>[],'other_images'=>[],'missing'=>[],'external'=>[]];
    $check=function(string $kind,string $name,string $image)use(&$report){$row=['name'=>$name,'image'=>$image,'status'=>'missing'];if($image&&preg_match('~^https?://~i',$image)){$row['status']='external';$report['external'][]=$row;}elseif($image&&Annam\Media::file($image)){$row['status']='local';}if($row['status']==='missing')$report['missing'][]=['kind'=>$kind]+$row;$report[$kind][]=$row;};
    foreach(['products'=>'catalog_menuitem','categories'=>'catalog_menucategory','other_images'=>'content_banner'] as $kind=>$table)foreach($db->rows("SELECT * FROM $table WHERE tenant_id=?",[$store->id()]) as $row)$check($kind,$row['name']??$row['title']??'Banner',$row['image']??'');
    $walk=function(array $data,string $prefix='')use(&$walk,$check){foreach($data as $key=>$value){if(is_array($value))$walk($value,$prefix.$key.'.');elseif(is_string($value)&&$value!==''&&in_array($key,['image','logo_url','billing_logo_url'],true))$check('other_images',$prefix.$key,$value);}};
    $walk($store->config['theme']);$walk($store->config['home_sections']);
    $report['counts']=['products'=>count($report['products']),'categories'=>count($report['categories']),'missing'=>count($report['missing']),'external'=>count($report['external'])];
    echo json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES).PHP_EOL;
}catch(Throwable $error){fwrite(STDERR,'Image audit failed: '.$error->getMessage().PHP_EOL);exit(1);}
