<?php
declare(strict_types=1);
namespace Annam;
final class Operations {
    public static function limit(Store $store,string $identity,int $maximum,int $seconds):void {
        $key=hash_hmac('sha256',$identity,getenv('APP_SECRET')?:'');$window=(int)(floor(time()/$seconds)*$seconds);
        $row=$store->db->one('INSERT INTO operations_ratelimitbucket(tenant_id,key,window_start,expires_at,attempts) VALUES(?,?,to_timestamp(?),to_timestamp(?),1) ON CONFLICT(tenant_id,key,window_start) DO UPDATE SET attempts=operations_ratelimitbucket.attempts+1 RETURNING attempts',[$store->id(),$key,$window,$window+$seconds]);
        if((int)$row['attempts']>$maximum)throw new HttpError(429,'Too many requests. Please try again later.');
    }
}
