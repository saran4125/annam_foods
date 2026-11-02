<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require dirname(__DIR__).'/src/bootstrap.php';
try{$store=new Annam\Store(new Annam\Database());$worker=new Annam\Worker($store);$result=['messages'=>getenv('MESSAGING_ENABLED')==='1'?$worker->dispatch():['offline'=>true],'payments'=>getenv('PAYMENTS_ENABLED')==='1'?$worker->payments():['offline'=>true]];if(getenv('PAYMENTS_ENABLED')==='1'){foreach($store->db->rows("SELECT id FROM payments_courierpayment WHERE tenant_id=? AND state IN ('ready','uncertain') ORDER BY updated_at LIMIT 20",[$store->id()]) as $row)try{(new Annam\CourierPayments($store))->reconcile($row['id']);}catch(Throwable){}}$store->db->rows("INSERT INTO operations_workerpulse(tenant_id,name,updated_at) VALUES(?,'php-cron',CURRENT_TIMESTAMP) ON CONFLICT(tenant_id,name) DO UPDATE SET updated_at=CURRENT_TIMESTAMP",[$store->id()]);$store->db->rows('DELETE FROM operations_ratelimitbucket WHERE tenant_id=? AND expires_at<CURRENT_TIMESTAMP',[$store->id()]);echo json_encode($result,JSON_THROW_ON_ERROR).PHP_EOL;}
catch(Throwable){fwrite(STDERR,"Background processing failed. Check private configuration and database connectivity.\n");exit(1);}
