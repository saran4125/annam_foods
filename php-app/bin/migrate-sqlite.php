<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli')exit(1);require dirname(__DIR__).'/src/bootstrap.php';
try{if(!in_array('--confirm-copy',$argv,true)||empty($argv[1]))throw new RuntimeException('Use migrate-sqlite.php /private/new-annam.sqlite --confirm-copy with the existing source connection configured.');echo json_encode(Annam\SqliteMigration::copy(new Annam\Database(),$argv[1]),JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR).PHP_EOL;}catch(Throwable $e){fwrite(STDERR,'Database copy failed: '.get_class($e).'. Check the private log. The source database was not changed.'.PHP_EOL);error_log('SQLite migration: '.$e->getMessage());exit(1);}
