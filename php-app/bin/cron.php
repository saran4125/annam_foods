<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require dirname(__DIR__).'/src/bootstrap.php';
try{$worker=new Annam\Worker(new Annam\Store(new Annam\Database()));echo json_encode(['messages'=>$worker->dispatch(),'payments'=>$worker->payments()],JSON_THROW_ON_ERROR).PHP_EOL;}
catch(Throwable){fwrite(STDERR,"Background processing failed. Check private configuration and database connectivity.\n");exit(1);}
