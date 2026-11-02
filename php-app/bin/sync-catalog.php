<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit(1);require dirname(__DIR__).'/src/bootstrap.php';
try{$store=new Annam\Store(new Annam\Database());Annam\Schema::ensure($store->db);echo json_encode((new Annam\CatalogSync($store))->run(in_array('--apply',$argv,true)),JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL;}catch(Throwable $e){fwrite(STDERR,'Catalog sync refused: '.$e->getMessage().PHP_EOL);exit(1);}
