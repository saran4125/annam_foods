<?php
declare(strict_types=1);
require dirname(__DIR__).'/src/bootstrap.php';
if(PHP_SAPI!=='cli'||!preg_match('~^sqlite:.*(?:test|preview).*~',getenv('DATABASE_DSN')?:''))exit(1);
putenv('BACKUP_PASSPHRASE='.bin2hex(random_bytes(32)));$prefix=sys_get_temp_dir().'/annam-sqlite-recovery-'.bin2hex(random_bytes(8));$archive=$prefix.'.enc';$extract=$prefix.'-extract';$restore=$prefix.'-restored.sqlite';$paths=[];
try{
 $db=new Annam\Database();$marker='snapshot-'.bin2hex(random_bytes(6));$id=$db->one('INSERT INTO php_login_attempt(tenant_id,fingerprint,attempted_at) VALUES(?,?,?) RETURNING id',[(new Annam\Store($db))->id(),$marker,date('c')])['id'];
 $result=Annam\Recovery::create($db,$archive);$verified=Annam\Recovery::verify($archive,$extract);if(!$verified['verified'])throw new RuntimeException('Archive not verified.');Annam\LocalRecovery::restore($extract.'/database.sqlite',$restore);$copy=new PDO('sqlite:'.$restore);if(!$copy->query('SELECT 1 FROM php_login_attempt WHERE id='.(int)$id)->fetchColumn())throw new RuntimeException('Committed WAL data missing from restored snapshot.');if($copy->query('PRAGMA integrity_check')->fetchColumn()!=='ok')throw new RuntimeException('Restore integrity failed.');echo "PASS encrypted SQLite backup includes committed WAL data and restores with valid integrity\n";
 $raw=file_get_contents($archive);$raw[90]=chr(ord($raw[90])^1);file_put_contents($archive.'.bad',$raw);try{Annam\Recovery::verify($archive.'.bad');throw new LogicException('Tampered backup accepted');}catch(RuntimeException){echo "PASS encrypted SQLite archive rejects tampering\n";}try{Annam\LocalRecovery::restore($extract.'/database.sqlite',$restore);throw new LogicException('Existing database overwritten');}catch(RuntimeException){echo "PASS restore refuses an existing database file\n";}
 $empty=$prefix.'-empty.sqlite';$emptyPdo=new PDO('sqlite:'.$empty);$emptyPdo=null;try{Annam\LocalRecovery::restore($empty,$prefix.'-invalid.sqlite');throw new LogicException('Empty database accepted');}catch(RuntimeException){echo "PASS empty SQLite snapshots are rejected before restoration\n";}unlink($empty);
 $db->rows('DELETE FROM php_login_attempt WHERE tenant_id=? AND id=?',[(new Annam\Store($db))->id(),$id]);
}finally{
 foreach([$archive,$archive.'.bad',$restore] as $file)if(is_file($file))unlink($file);if(is_dir($extract)){foreach(new RecursiveIteratorIterator(new RecursiveDirectoryIterator($extract,FilesystemIterator::SKIP_DOTS),RecursiveIteratorIterator::CHILD_FIRST) as $f)$f->isDir()?rmdir($f->getPathname()):unlink($f->getPathname());rmdir($extract);}
}
