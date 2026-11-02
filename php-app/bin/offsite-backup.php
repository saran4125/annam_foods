<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit(1);require dirname(__DIR__).'/src/bootstrap.php';
try{
 $origin=rtrim(getenv('SUPABASE_BACKUP_URL')?:'','/');$key=getenv('SUPABASE_BACKUP_SERVICE_KEY')?:'';$bucket=getenv('SUPABASE_BACKUP_BUCKET')?:'annam-private-backups';
 if(!preg_match('~^https://[a-z0-9-]+\.supabase\.co$~D',$origin)||!$key||!preg_match('/^[a-z0-9-]+$/D',$bucket))throw new RuntimeException('Configure a private Supabase Storage bucket and service credentials.');
 $path=ANNAM_ROOT.'/storage/offsite-'.bin2hex(random_bytes(8)).'.enc';
 try{Annam\Recovery::create(new Annam\Database(),$path);Annam\Recovery::verify($path);$file=fopen($path,'rb');$object='annam-'.gmdate('Ymd-His').'-'.bin2hex(random_bytes(6)).'.enc';$curl=curl_init($origin.'/storage/v1/object/'.$bucket.'/'.$object);curl_setopt_array($curl,[CURLOPT_UPLOAD=>true,CURLOPT_CUSTOMREQUEST=>'POST',CURLOPT_INFILE=>$file,CURLOPT_INFILESIZE=>filesize($path),CURLOPT_HTTPHEADER=>['Authorization: Bearer '.$key,'apikey: '.$key,'Content-Type: application/octet-stream','x-upsert: false'],CURLOPT_RETURNTRANSFER=>true,CURLOPT_CONNECTTIMEOUT=>10,CURLOPT_TIMEOUT=>300,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,CURLOPT_PROTOCOLS=>CURLPROTO_HTTPS]);$response=curl_exec($curl);$status=curl_getinfo($curl,CURLINFO_RESPONSE_CODE);curl_close($curl);fclose($file);if($response===false||$status<200||$status>=300)throw new RuntimeException('Offsite storage upload failed.');echo json_encode(['uploaded'=>true,'object'=>$object,'sha256'=>hash_file('sha256',$path)]).PHP_EOL;}finally{if(is_file($path))unlink($path);}
}catch(Throwable){fwrite(STDERR,"Offsite backup failed. Check private storage configuration. No credentials were printed.\n");exit(1);}
