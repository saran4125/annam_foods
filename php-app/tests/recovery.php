<?php
require dirname(__DIR__).'/src/bootstrap.php';
if(PHP_SAPI!=='cli'||!preg_match('/dbname=[^;]*(?:preview|test)[^;]*(?:;|$)/i',getenv('DATABASE_DSN')?:''))exit(1);
putenv('BACKUP_PASSPHRASE='.bin2hex(random_bytes(32)));
$file='/tmp/parity-recovery-'.bin2hex(random_bytes(6)).'.enc';$extract='/tmp/parity-recovery-'.bin2hex(random_bytes(6));
$result=Annam\Recovery::create(new Annam\Database(),$file);$verified=Annam\Recovery::verify($file,$extract);echo json_encode(['created'=>$result,'verified'=>$verified]).PHP_EOL;
$raw=file_get_contents($file);$raw[80]=chr(ord($raw[80])^1);$bad=$file.'.bad';file_put_contents($bad,$raw);try{Annam\Recovery::verify($bad);throw new RuntimeException('Tampering accepted');}catch(RuntimeException $e){if($e->getMessage()==='Tampering accepted')throw $e;echo "PASS encrypted archive rejects tampering\n";}
$db=new Annam\Database();try{$db->transaction(function()use($db,$extract){$db->rows('DROP SCHEMA public CASCADE');$db->rows('CREATE SCHEMA public');$db->schemaScript(file_get_contents(ANNAM_ROOT.'/resources/schema.sql'));Annam\Recovery::restoreData($db,$extract.'/database.jsonl');$store=new Annam\Store($db);echo 'PASS restored catalog '.count($store->items()).' products'.PHP_EOL;throw new LogicException('rollback rehearsal');});}catch(LogicException $e){if($e->getMessage()!=='rollback rehearsal')throw $e;echo "PASS restore rehearsal rolled back\n";}

foreach([$file,$bad] as $path)if(is_file($path))unlink($path);foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator($extract,FilesystemIterator::SKIP_DOTS),RecursiveIteratorIterator::CHILD_FIRST) as $entry)$entry->isDir()?rmdir($entry->getPathname()):unlink($entry->getPathname());rmdir($extract);
