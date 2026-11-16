<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit(1);}
require dirname(__DIR__).'/src/bootstrap.php';
try{
 if(!in_array('--new-store',$argv,true))throw new RuntimeException('Use --new-store only for a fresh installation with the reviewed seed database.');
 if(is_file(Annam\Installation::file()))throw new RuntimeException('Private installation settings already exist; keep them and the existing database.');
 $db=new Annam\Database();if(!$db->isSqlite())throw new RuntimeException('Fresh local setup requires SQLite.');
 foreach(['auth_user','orders_customer','orders_order','tenancy_tenantsecrets','payments_razorpayconnection'] as $table)if((int)$db->one('SELECT COUNT(*) AS n FROM '.$table)['n'])throw new RuntimeException('Existing accounts or operational data found. Fresh initialization is refused.');
 $store=new Annam\Store($db);$path=ANNAM_ROOT.'/SETUP-ACCESS.txt';if(file_exists($path))throw new RuntimeException('A private setup access file already exists.');
 $token=bin2hex(random_bytes(24));$config=['version'=>1,'complete'=>false,'setup_token_hash'=>hash('sha256',$token),'APP_SECRET'=>bin2hex(random_bytes(32)),'SECRETS_KEY'=>strtr(base64_encode(random_bytes(32)),'+/','-_'),'APP_ENV'=>'production','STORE_SLUG'=>$store->tenant['slug'],'PAYMENTS_ENABLED'=>'0','MESSAGING_ENABLED'=>'0','REQUIRE_CRON'=>'0'];
 // Serialize initial setup so two CLI invocations cannot replace each other's keys.
 $lock=fopen(ANNAM_ROOT.'/storage/setup.lock','c');if(!$lock||!flock($lock,LOCK_EX))throw new RuntimeException('Setup is busy.');
 try{
  if(is_file(Annam\Installation::file())||file_exists($path))throw new RuntimeException('Setup was initialized by another process.');
  $handle=fopen($path,'x');if(!$handle)throw new RuntimeException('Cannot create the private setup access file.');chmod($path,0600);
  fwrite($handle,"PRIVATE — keep outside the public web root.\nOpen your HTTPS domain/setup/ and create your own owner login.\nOne-time setup code: ".$token."\nThe code stops working after setup.\n");fclose($handle);
  Annam\Installation::save($config);
 }finally{flock($lock,LOCK_UN);fclose($lock);}
 echo "Fresh SQLite setup initialized. Read the private SETUP-ACCESS.txt file, then open your HTTPS domain/setup/. No password or private key was printed.\n";
}catch(Throwable $e){fwrite(STDERR,'Initialization refused: '.$e->getMessage().PHP_EOL);exit(1);}
