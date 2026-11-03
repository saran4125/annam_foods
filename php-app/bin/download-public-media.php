<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit(1);require dirname(__DIR__).'/src/bootstrap.php';
try{$limit=PHP_INT_MAX;foreach($argv as $arg)if(preg_match('/^--limit=(\d+)$/D',$arg,$m))$limit=(int)$m[1];$result=Annam\PublicMedia::download($limit);echo json_encode($result,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL;exit($result['verified_local_images']===$result['source_assets']?0:2);}catch(Throwable $error){fwrite(STDERR,'Public media recovery failed: '.$error->getMessage().PHP_EOL);exit(1);}
