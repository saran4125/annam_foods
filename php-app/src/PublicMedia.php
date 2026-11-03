<?php
declare(strict_types=1);
namespace Annam;
/** Public catalog-photo recovery only. Never scans invoices, customers or private uploads. */
final class PublicMedia {
    public static function root():string {return getenv('PUBLIC_MEDIA_ROOT')?:(Installation::config()?Media::root():dirname(ANNAM_ROOT).'/media');}
    public static function manifest():string{return ANNAM_ROOT.'/resources/public-media.json';}
    public static function inventory():array {
        $source=json_decode(file_get_contents(ANNAM_ROOT.'/resources/source-catalog.json'),true,512,JSON_THROW_ON_ERROR);$assets=[];
        $add=function(string $url,array $reference,string $folder)use(&$assets){self::url($url);$key=hash('sha256',$url);if(!isset($assets[$key]))$assets[$key]=['url'=>$url,'folder'=>$folder,'references'=>[],'status'=>'pending','path'=>null,'sha256'=>null];$assets[$key]['references'][]=$reference;};
        foreach($source['products'] as $product)foreach($product['images']??[] as $index=>$url)$add($url,['kind'=>'product','source_id'=>(string)$product['source_id'],'name'=>$product['name'],'image_index'=>$index],'catalog');
        foreach($source['categories'] as $category)if(!empty($category['image']))$add($category['image'],['kind'=>'category','source_id'=>(string)$category['source_id'],'name'=>$category['name'],'slug'=>$category['slug']],'categories');
        if(!empty($source['brand']['logo']))$add($source['brand']['logo'],['kind'=>'brand','name'=>'Annam Foods source logo'],'brand');
        $old=is_file(self::manifest())?json_decode(file_get_contents(self::manifest()),true,512,JSON_THROW_ON_ERROR):[];
        foreach($assets as $key=>&$asset)if(isset($old['assets'][$key]))foreach(['status','path','sha256','bytes','error'] as $field)if(array_key_exists($field,$old['assets'][$key]))$asset[$field]=$old['assets'][$key][$field];unset($asset);
        return ['version'=>1,'source'=>$source['source'],'source_snapshot'=>$source['fetched_at'],'description'=>'Original public source assets. Only verified downloads may be assigned to catalog records.','assets'=>$assets];
    }
    public static function url(string $url):void {$parts=parse_url($url);if(($parts['scheme']??'')!=='https'||!in_array(strtolower($parts['host']??''),['cdn.commmerce.com','www.annamfood.in','annamfood.in'],true)||isset($parts['user'])||isset($parts['pass'])||isset($parts['port']))throw new \RuntimeException('Only approved original public image hosts may be downloaded.');}
    public static function store(array $asset,string $bytes,string $root):array {
        self::url($asset['url']);$image=@getimagesizefromstring($bytes);$extension=$image?([IMAGETYPE_JPEG=>'jpg',IMAGETYPE_PNG=>'png',IMAGETYPE_GIF=>'gif',IMAGETYPE_WEBP=>'webp',19=>'avif'][$image[2]]??null):null;
        if(!$extension||strlen($bytes)>15728640||$image[0]*$image[1]>50000000)throw new \RuntimeException('The source did not return a supported image within safe size limits.');
        if(!in_array($asset['folder'],['catalog','categories','brand'],true))throw new \RuntimeException('Invalid public media destination.');
        $relative=$asset['folder'].'/'.substr(hash('sha256',$asset['url']),0,32).'.'.$extension;$file=$root.'/'.$relative;if(is_link($file))throw new \RuntimeException('Image destination must not be a symlink.');if(!is_dir(dirname($file)))mkdir(dirname($file),0755,true);$tmp=$file.'.'.bin2hex(random_bytes(6));if(file_put_contents($tmp,$bytes,LOCK_EX)===false)throw new \RuntimeException('Cannot save public image.');chmod($tmp,0644);if(!rename($tmp,$file))throw new \RuntimeException('Cannot activate public image.');
        unset($asset['error']);return array_replace($asset,['status'=>'downloaded','path'=>$relative,'sha256'=>hash('sha256',$bytes),'bytes'=>strlen($bytes)]);
    }
    public static function verified(array $asset,string $root):bool {
        $relative=$asset['path']??'';if(($asset['status']??'')!=='downloaded'||!preg_match('~^(catalog|categories|brand)/[a-f0-9]{32}\.(jpg|png|gif|webp|avif)$~D',$relative))return false;
        $base=realpath($root);$file=realpath($root.'/'.$relative);return $base&&$file&&str_starts_with($file,$base.'/')&&is_file($file)&&!is_link($root.'/'.$relative)&&hash_equals((string)$asset['sha256'],hash_file('sha256',$file));
    }
    public static function download(int $limit=PHP_INT_MAX):array {
        $manifest=self::inventory();$root=self::root();$attempted=$recovered=0;
        foreach($manifest['assets'] as &$asset){if(self::verified($asset,$root))continue;if($attempted++>=$limit)break;
            try{$bytes='';$curl=curl_init($asset['url']);curl_setopt_array($curl,[CURLOPT_RETURNTRANSFER=>false,CURLOPT_CONNECTTIMEOUT=>10,CURLOPT_TIMEOUT=>30,CURLOPT_FOLLOWLOCATION=>false,CURLOPT_PROTOCOLS=>CURLPROTO_HTTPS,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,CURLOPT_USERAGENT=>'Mozilla/5.0 (Annam Foods owner media recovery)',CURLOPT_HTTPHEADER=>['Referer: https://www.annamfood.in/','Accept: image/avif,image/webp,image/png,image/jpeg,image/gif'],CURLOPT_WRITEFUNCTION=>function($handle,$chunk)use(&$bytes){if(strlen($bytes)+strlen($chunk)>15728640)return 0;$bytes.=$chunk;return strlen($chunk);}]);$ok=curl_exec($curl);$status=curl_getinfo($curl,CURLINFO_RESPONSE_CODE);$error=curl_error($curl);curl_close($curl);if($ok===false||$status!==200)throw new \RuntimeException('HTTP '.$status.': '.($error?:'Original image unavailable.'));$asset=self::store($asset,$bytes,$root);$recovered++;}
            catch(\RuntimeException $error){$asset['status']='unavailable';$asset['error']=substr($error->getMessage(),0,220);}
        }unset($asset);$tmp=self::manifest().'.'.bin2hex(random_bytes(6));if(file_put_contents($tmp,json_encode($manifest,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE)."\n",LOCK_EX)===false)throw new \RuntimeException('Cannot save the public media inventory.');chmod($tmp,0644);if(!rename($tmp,self::manifest()))throw new \RuntimeException('Cannot activate the public media inventory.');
        return self::summary($manifest,$root)+['recovered_this_run'=>$recovered];
    }
    public static function summary(array $manifest,string $root):array {$verified=0;$unavailable=0;foreach($manifest['assets'] as $asset){if(self::verified($asset,$root))$verified++;elseif(($asset['status']??'')==='unavailable')$unavailable++;}return ['source_assets'=>count($manifest['assets']),'verified_local_images'=>$verified,'unavailable'=>$unavailable,'pending'=>count($manifest['assets'])-$verified-$unavailable];}
    public static function apply(\PDO $db,string $root,?array $manifest=null):array {
        $manifest??=self::inventory();$changed=0;$skipped=0;$storeId=$db->query("SELECT id FROM tenancy_tenant WHERE slug='annam'")->fetchColumn();if(!$storeId)throw new \RuntimeException('Annam store missing.');$db->beginTransaction();
        try{foreach($manifest['assets'] as $asset){if(!self::verified($asset,$root))continue;foreach($asset['references'] as $reference){if($reference['kind']==='product'&&$reference['image_index']===0){$query=$db->prepare("UPDATE catalog_menuitem SET image=? WHERE tenant_id=? AND retailer_id=? AND (image='' OR image=?)");$query->execute([$asset['path'],$storeId,$reference['source_id'],$asset['url']]);$changed+=$query->rowCount();}
                elseif($reference['kind']==='category'){$query=$db->prepare("UPDATE catalog_menucategory SET image=? WHERE tenant_id=? AND slug=? AND (image='' OR image=?)");$query->execute([$asset['path'],$storeId,$reference['slug'],$asset['url']]);$changed+=$query->rowCount();}}}$db->commit();return ['image_references_updated'=>$changed];}catch(\Throwable $error){$db->rollBack();throw $error;}
    }
}
