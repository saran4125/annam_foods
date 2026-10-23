<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require dirname(__DIR__).'/src/bootstrap.php';
try{
    $audit=new Annam\Audit(new Annam\Store(new Annam\Database()));$args=getopt('',['baseline:','compare:','readiness']);
    if(isset($args['readiness'])){$report=$audit->readiness();echo json_encode($report,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES).PHP_EOL;exit($report['database_checks_passed']?0:1);}
    $current=$audit->fingerprints();if(isset($args['baseline'])){$path=$args['baseline'];if(!str_starts_with($path,'/')||is_file($path))throw new RuntimeException('Use a new absolute private baseline path.');$old=umask(0077);try{if(file_put_contents($path,json_encode($current,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR),LOCK_EX)===false)throw new RuntimeException('Cannot write baseline.');}finally{umask($old);}echo "Private migration baseline saved.\n";}
    elseif(isset($args['compare'])){$previous=json_decode(file_get_contents($args['compare']),true,64,JSON_THROW_ON_ERROR);if(($previous['store']??'')!==$current['store'])throw new RuntimeException('Baseline belongs to another store.');$changed=[];foreach($current['tables'] as $table=>$value)if(($previous['tables'][$table]??null)!==$value)$changed[]=$table;echo json_encode(['identical'=>!$changed,'changed_tables'=>$changed],JSON_PRETTY_PRINT).PHP_EOL;exit($changed?1:0);}
    else echo json_encode($current,JSON_PRETTY_PRINT).PHP_EOL;
}catch(Throwable){fwrite(STDERR,"Migration audit failed. Check the private database, schema and report path.\n");exit(1);}
