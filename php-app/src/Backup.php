<?php
declare(strict_types=1);
namespace Annam;
final class Backup {
    public function __construct(private Store $store) {}
    public function references(): array {
        $refs=[];$outside=[];$add=function(string $value)use(&$refs,&$outside){if(!$value)return;if(preg_match('~^https?://~i',$value)){$outside[]=$value;return;}$relative=Media::relative($value);if($relative)$refs[$relative]=true;};
        foreach(['catalog_menuitem','catalog_menucategory','content_banner'] as $table)foreach($this->store->db->rows("SELECT image FROM $table WHERE tenant_id=?",[$this->store->id()]) as $row)$add($row['image']);
        $walk=function(array $value)use(&$walk,$add){foreach($value as $key=>$entry){if(is_array($entry))$walk($entry);elseif(is_string($entry)&&in_array($key,['image','logo_url','billing_logo_url'],true))$add($entry);}};$walk($this->store->config['theme']);$walk($this->store->config['home_sections']);
        foreach($this->store->db->rows('SELECT seller FROM billing_invoice WHERE tenant_id=?',[$this->store->id()]) as $row){$seller=json_decode($row['seller'],true,64,JSON_THROW_ON_ERROR);$url=$seller['logo_url']??'';$add($url==='/static/branding/annam-bill-logo.png'?'/media/brand/annam-bill-logo.png':$url);}
        foreach($this->store->db->rows('SELECT id,content_type FROM content_storefrontimage WHERE tenant_id=?',[$this->store->id()]) as $row){$ext=['image/jpeg'=>'jpg','image/png'=>'png','image/webp'=>'webp'][$row['content_type']]??null;if($ext)$add('website/'.$this->store->id().'/'.$row['id'].'.'.$ext);}
        $add($this->store->logo());$files=[];$missing=[];foreach(array_keys($refs) as $relative){$file=Media::file($relative);if($file)$files[$relative]=$file;else $missing[]=$relative;}ksort($files);sort($missing);return ['files'=>$files,'missing'=>$missing,'external'=>array_values(array_unique($outside))];
    }
    public function download(): void {
        if(!class_exists('ZipArchive'))throw new HttpError(503,'Enable the PHP ZIP extension to export photos.');$refs=$this->references();$path=tempnam(ANNAM_ROOT.'/storage','media-backup-');if(!$path)throw new HttpError(503,'Private backup folder is not writable.');
        try{$zip=new \ZipArchive();if($zip->open($path,\ZipArchive::CREATE|\ZipArchive::OVERWRITE)!==true)throw new HttpError(503,'Could not build the backup.');$hashes=[];$size=0;foreach($refs['files'] as $name=>$file){$size+=filesize($file);if($size>268435456)throw new HttpError(422,'The media backup exceeds 256 MB. Use the hosting file manager backup.');$zip->addFile($file,'media/'.$name);$hashes[$name]=hash_file('sha256',$file);}$zip->addFromString('media/.htaccess',file_get_contents(ANNAM_ROOT.'/deploy/media.htaccess'));$zip->addFromString('REPORT.json',json_encode(['generated_at'=>date('c'),'file_count'=>count($hashes),'sha256'=>$hashes,'missing'=>$refs['missing'],'external_images'=>$refs['external']],JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));$zip->close();header('Content-Type: application/zip');header('Content-Disposition: attachment; filename="annam-media-'.date('Ymd-His').'.zip"');header('Content-Length: '.filesize($path));readfile($path);}finally{if(is_file($path))unlink($path);}
    }
}
