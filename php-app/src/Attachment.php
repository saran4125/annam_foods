<?php
declare(strict_types=1);
namespace Annam;
/** Authenticated, scoped Meta attachment proxy. No arbitrary URL input. */
final class Attachment {
    public static function serve(Store $store,int $id): void {
        $message=$store->row('messaging_whatsappmessage',$id);$mediaId=$message['media_id'];if(!ctype_digit($mediaId)||strlen($mediaId)>80)throw new HttpError(404,'Attachment unavailable.');
        $secrets=(new Messaging($store))->secrets();$token=Crypto::decrypt($secrets['wa_token_enc']);if(!$token)throw new HttpError(422,'Configure the Meta token to read attachments.');
        $data=Http::json('GET','https://graph.facebook.com/v23.0/'.$mediaId,['Authorization'=>'Bearer '.$token]);$url=$data['url']??'';$host=parse_url($url,PHP_URL_HOST)??'';
        if(!in_array($host,['lookaside.fbsbx.com','lookaside.facebook.com','mmg.whatsapp.net'],true)||parse_url($url,PHP_URL_SCHEME)!=='https'||!extension_loaded('curl'))throw new HttpError(422,'Unsupported attachment source.');if(($data['file_size']??0)>16777216)throw new HttpError(413,'Attachment is too large.');
        $bytes='';$curl=curl_init($url);curl_setopt_array($curl,[CURLOPT_HTTPHEADER=>['Authorization: Bearer '.$token],CURLOPT_FOLLOWLOCATION=>false,CURLOPT_PROTOCOLS=>CURLPROTO_HTTPS,CURLOPT_CONNECTTIMEOUT=>5,CURLOPT_TIMEOUT=>15,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,CURLOPT_WRITEFUNCTION=>function($handle,$chunk)use(&$bytes){if(strlen($bytes)+strlen($chunk)>16777216)return 0;$bytes.=$chunk;return strlen($chunk);}]);$ok=curl_exec($curl);$status=curl_getinfo($curl,CURLINFO_RESPONSE_CODE);curl_close($curl);if(!$ok||$status!==200)throw new HttpError(502,'Meta could not return this attachment.');
        $type=(new \finfo(FILEINFO_MIME_TYPE))->buffer($bytes);$inline=in_array($type,['image/jpeg','image/png','image/webp','image/gif'],true);$filename=preg_replace('/[^a-zA-Z0-9._-]/','_',basename($message['filename']?:'attachment'));
        header('Content-Type: '.($inline?$type:'application/octet-stream'));header('Content-Disposition: '.($inline?'inline':'attachment').'; filename="'.$filename.'"');header("Content-Security-Policy: default-src 'none'; sandbox");header('Content-Length: '.strlen($bytes));echo $bytes;
    }
}
