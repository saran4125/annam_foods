<?php
declare(strict_types=1);
namespace Annam;

/** Fernet wire compatibility with cryptography.fernet used by existing records. */
final class Crypto {
    private static function key(): string {
        $value=getenv('SECRETS_KEY')?:'';
        $key=base64_decode(strtr($value,'-_','+/'),true);
        if(($key===false||strlen($key)!==32)&&strlen($value)>=32)$key=hash('sha256',$value,true);
        if($key===false||strlen($key)!==32) throw new HttpError(503,'The server encryption key is missing or invalid.');
        return $key;
    }
    public static function encrypt(string $value): string {
        if($value==='') return '';
        $key=self::key();$iv=random_bytes(16);
        $cipher=openssl_encrypt($value,'aes-128-cbc',substr($key,16),OPENSSL_RAW_DATA,$iv);
        if($cipher===false) throw new HttpError(503,'Secret encryption failed.');
        $data="\x80".pack('N2',0,time()).$iv.$cipher;
        return strtr(base64_encode($data.hash_hmac('sha256',$data,substr($key,0,16),true)),'+/','-_');
    }
    public static function decrypt(string $value): string {
        if($value==='') return '';
        $key=self::key();$raw=base64_decode(strtr($value,'-_','+/'),true);
        if($raw===false||strlen($raw)<73||$raw[0]!=="\x80"||!hash_equals(substr($raw,-32),hash_hmac('sha256',substr($raw,0,-32),substr($key,0,16),true))) throw new HttpError(503,'Saved credentials could not be decrypted. Check SECRETS_KEY.');
        $result=openssl_decrypt(substr($raw,25,-32),'aes-128-cbc',substr($key,16),OPENSSL_RAW_DATA,substr($raw,9,16));
        if($result===false) throw new HttpError(503,'Saved credentials could not be decrypted.');
        return $result;
    }
}
