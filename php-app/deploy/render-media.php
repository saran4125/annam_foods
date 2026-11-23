<?php
declare(strict_types=1);
// Restore committed PUBLIC artwork only, for the disposable Render preview.
if(PHP_SAPI!=='cli')exit(1);
require dirname(__DIR__).'/src/bootstrap.php';
$previewRoot=getenv('PREVIEW_DATA_ROOT')?:'/tmp/annam-php-preview';
if(!in_array($previewRoot,['/tmp/annam-php-preview','/var/data/annam-php-preview'],true)||getenv('APP_ENV')!=='preview'||getenv('DATABASE_DSN')!=='sqlite:'.$previewRoot.'/annam.sqlite')throw new RuntimeException('This restore is only for the temporary PHP preview.');
$store=new Annam\Store(new Annam\Database());
Annam\Media::restore($store);
$root=Annam\Media::root();$source=dirname(ANNAM_ROOT).'/media';$copied=0;
foreach(['brand','catalog','categories','menu','site'] as $folder){
    if(!is_dir($source.'/'.$folder))continue;
    foreach(new DirectoryIterator($source.'/'.$folder) as $file){
        if(!$file->isFile()||$file->isLink()||!preg_match('/^[a-zA-Z0-9_-]+\.(png|jpe?g|webp|gif|avif|ico)$/iD',$file->getFilename()))continue;
        $target=$root.'/'.$folder.'/'.$file->getFilename();
        if(file_exists($target))continue; // Existing owner artwork takes priority.
        if(!is_dir(dirname($target)))mkdir(dirname($target),0750,true);
        if(!copy($file->getPathname(),$target))throw new RuntimeException('Cannot restore public preview image.');
        $copied++;
    }
}
// Only verified originals can fill empty catalog/category image fields.
// This preserves non-empty owner uploads and the existing financial/customer data.
$pdo=new PDO(getenv('DATABASE_DSN'),null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
$result=Annam\PublicMedia::apply($pdo,$root);
echo json_encode(['public_images_restored'=>$copied]+$result,JSON_THROW_ON_ERROR).PHP_EOL;
