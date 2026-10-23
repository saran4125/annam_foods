<?php
declare(strict_types=1);
// Developer packaging utility; never served through the public directory.
if (PHP_SAPI !== 'cli') exit(1);
if (!class_exists('ZipArchive')) { fwrite(STDERR,"Enable PHP's zip extension to create the review archive.\n"); exit(1); }
$root=dirname(__DIR__);
if (!is_dir($root.'/dist')) mkdir($root.'/dist',0750,true);
$output=$root.'/dist/annam-php-preview.zip';
$zip=new ZipArchive();
if ($zip->open($output,ZipArchive::CREATE|ZipArchive::OVERWRITE)!==true) throw new RuntimeException('Cannot create archive.');
$hashes=[];
foreach (['src','views','resources','deploy','bin','tests','public/assets'] as $directory) {
    foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root.'/'.$directory,FilesystemIterator::SKIP_DOTS)) as $file) {
        if (!$file->isFile() || $file->isLink()) continue;
        $relative=substr($file->getPathname(),strlen($root)+1);
        if (!in_array(strtolower($file->getExtension()),['php','py','md','txt','css','js','png','jpg','webp','svg','avif','gif','json','htaccess'],true)) continue;
        $zip->addFile($file->getPathname(),'annam-php-preview/'.$relative);
        $hashes[$relative]=hash_file('sha256',$file->getPathname());
    }
}
foreach (['README.md','ARCHITECTURE.md','.env.example','router.php','hosting-check.php','public/.htaccess','public/index.php','storage/sessions/.gitkeep','storage/logs/.gitkeep'] as $relative) {
    $zip->addFile($root.'/'.$relative,'annam-php-preview/'.$relative);
    $hashes[$relative]=hash_file('sha256',$root.'/'.$relative);
}
$zip->addFile($root.'/deploy/media.htaccess','annam-php-preview/public/media/.htaccess');
$zip->addFromString('annam-php-preview/CHECKSUMS.json',json_encode($hashes,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));
$zip->close();
echo "Review archive created. No .env, database, uploaded media, sessions or logs included.\n";
