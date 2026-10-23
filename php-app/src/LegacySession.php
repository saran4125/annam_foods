<?php
declare(strict_types=1);
namespace Annam;

/** Read-only guest order access across the Django-to-PHP cutover. No admin login migration. */
final class LegacySession {
    public static function decode(string $value,string $secret): ?array {
        $parts=explode(':',$value);if(count($parts)!==3||$secret==='')return null;
        [$payload,$timestamp,$signature]=$parts;$key=hash('sha256','django.contrib.sessions.SessionStoresigner'.$secret,true);
        $expected=rtrim(strtr(base64_encode(hash_hmac('sha256',$payload.':'.$timestamp,$key,true)),'+/','-_'),'=');if(!hash_equals($expected,$signature))return null;
        $compressed=str_starts_with($payload,'.');$raw=base64_decode(strtr($compressed?substr($payload,1):$payload,'-_','+/'),true);if($raw===false)return null;
        if($compressed)$raw=@gzuncompress($raw,1048576);if($raw===false||strlen($raw)>1048576)return null;
        try{$data=json_decode($raw,true,64,JSON_THROW_ON_ERROR);return is_array($data)?$data:null;}catch(\JsonException){return null;}
    }
    public static function browser(int $tenantId): ?string {
        $key=$_COOKIE['sessionid']??'';if(!is_string($key)||!preg_match('/^[a-z0-9]{32}$/D',$key)||!(getenv('DJANGO_SECRET_KEY')?:''))return null;
        $row=(new Database())->one('SELECT session_data FROM django_session WHERE session_key=? AND expire_date>CURRENT_TIMESTAMP',[$key]);if(!$row)return null;
        $data=self::decode($row['session_data'],getenv('DJANGO_SECRET_KEY'));$browser=$data['checkout.browser.'.$tenantId]??null;
        return is_string($browser)&&preg_match('/^[a-f0-9]{32}$/D',$browser)?$browser:null;
    }
}
