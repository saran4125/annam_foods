<?php
declare(strict_types=1);
namespace Annam;
final class Media {
    public static function root(): string {$root=getenv('MEDIA_ROOT')?:'public/media';return str_starts_with($root,'/')?$root:ANNAM_ROOT.'/'.$root;}
    public static function relative(string $name): ?string {
        $name=rawurldecode($name);if(str_starts_with($name,'media/'))$name=substr($name,6);if(str_starts_with($name,'/media/'))$name=substr($name,7);
        if(!$name||str_starts_with($name,'/')||str_contains($name,'..')||str_contains($name,'\\')||preg_match('/[\x00-\x1f\x7f:?#]/',$name)||!preg_match('/\.(png|jpe?g|webp|gif|svg|avif)$/i',$name))return null;return $name;
    }
    public static function file(string $name): ?string {
        $relative=self::relative($name);if(!$relative)return null;$root=realpath(self::root());$path=realpath(self::root().'/'.$relative);return $root&&$path&&str_starts_with($path,$root.'/')&&is_file($path)?$path:null;
    }
    public static function restore(Store $store): array {
        $root=self::root();$restored=0;$missing=[];
        foreach(new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator(ANNAM_ROOT.'/resources/public-files',\FilesystemIterator::SKIP_DOTS)) as $file){if(!$file->isFile()||$file->isLink())continue;$relative=substr($file->getPathname(),strlen(ANNAM_ROOT.'/resources/public-files/'));$dest=$root.'/'.$relative;if(!is_file($dest)){if(!is_dir(dirname($dest)))mkdir(dirname($dest),0750,true);if(!copy($file->getPathname(),$dest))throw new \RuntimeException('Cannot restore bundled media.');$restored++;}}
        foreach($store->db->rows('SELECT id,content_type,data FROM content_storefrontimage WHERE tenant_id=?',[$store->id()]) as $image){$ext=['image/jpeg'=>'jpg','image/png'=>'png','image/webp'=>'webp'][$image['content_type']]??null;if(!$ext)continue;$path=$root.'/website/'.$store->id().'/'.$image['id'].'.'.$ext;if(is_file($path))continue;$data=$image['data'];if(is_resource($data))$data=stream_get_contents($data);if(!is_string($data)||strlen($data)>3145728||!@getimagesizefromstring($data)){$missing[]=$image['id'];continue;}if(!is_dir(dirname($path)))mkdir(dirname($path),0750,true);if(file_put_contents($path,$data,LOCK_EX)===false)throw new \RuntimeException('Cannot restore website photo.');$restored++;}
        return ['restored'=>$restored,'unrecoverable_images'=>$missing];
    }
    public static function asset(Store $store,string $id,bool $staff): void {
        $url='/platform/assets/'.$store->tenant['slug'].'/'.$id.'/';$published=$store->config['storefront_design']['published']['images']??[];
        if(!$staff&&!in_array($url,$published,true))throw new HttpError(404,'Image not found.');
        $image=$store->db->one('SELECT * FROM content_storefrontimage WHERE tenant_id=? AND id=?',[$store->id(),$id])??throw new HttpError(404,'Image not found.');$ext=['image/jpeg'=>'jpg','image/png'=>'png','image/webp'=>'webp'][$image['content_type']]??throw new HttpError(404,'Image unavailable.');
        $file=self::file('website/'.$store->id().'/'.$id.'.'.$ext);header('Content-Type: '.$image['content_type']);header('Cache-Control: '.($staff?'private, no-store':'public, max-age=3600'));if($file){header('Content-Length: '.filesize($file));readfile($file);}else{$data=$image['data'];if(is_resource($data))$data=stream_get_contents($data);header('Content-Length: '.strlen($data));echo $data;}
    }
    public static function serve(string $relative): void {
        if(str_starts_with(rawurldecode($relative),'website/'))throw new HttpError(404,'Image not found.');$file=self::file($relative)??throw new HttpError(404,'Image not found.');$mime=(new \finfo(FILEINFO_MIME_TYPE))->file($file);if(!in_array($mime,['image/png','image/jpeg','image/webp','image/gif','image/svg+xml','image/avif'],true))throw new HttpError(404,'Image unavailable.');header('Content-Type: '.$mime);header('Cache-Control: public, max-age=3600');header('Content-Length: '.filesize($file));readfile($file);
    }
}
