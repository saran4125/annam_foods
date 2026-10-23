<?php
declare(strict_types=1);
namespace Annam;

final class Http {
    /** Injection is confined to CLI tests; never selected by browser input. */
    public static ?\Closure $transport=null;
    public static function publicUrl(string $url): void {
        $parts=parse_url($url);if(($parts['scheme']??'')!=='https'||empty($parts['host'])||isset($parts['user'])||isset($parts['pass'])||isset($parts['fragment'])||isset($parts['port'])&&$parts['port']!==443)throw new HttpError(422,'Use a public HTTPS webhook URL without credentials.');
        $records=dns_get_record($parts['host'],DNS_A|DNS_AAAA);if(!$records)throw new HttpError(422,'The webhook hostname could not be resolved.');foreach($records as $record){$ip=$record['ip']??$record['ipv6']??'';if(!filter_var($ip,FILTER_VALIDATE_IP,FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE))throw new HttpError(422,'Webhook addresses must resolve to public servers.');}
    }
    public static function json(string $method,string $url,array $headers=[],?array $body=null,bool $custom=false): array {
        if(PHP_SAPI==='cli'&&self::$transport)return (self::$transport)($method,$url,$headers,$body);
        if(!extension_loaded('curl'))throw new HttpError(503,'Enable the PHP cURL extension for provider connections.');
        if($custom)self::publicUrl($url);
        $curl=curl_init($url);$list=['Accept: application/json'];foreach($headers as $key=>$value)$list[]=$key.': '.$value;
        if($body!==null)$list[]='Content-Type: application/json';$response='';
        $options=[CURLOPT_CUSTOMREQUEST=>$method,CURLOPT_HTTPHEADER=>$list,CURLOPT_FOLLOWLOCATION=>false,CURLOPT_CONNECTTIMEOUT=>5,CURLOPT_TIMEOUT=>12,CURLOPT_SSL_VERIFYPEER=>true,CURLOPT_SSL_VERIFYHOST=>2,CURLOPT_PROTOCOLS=>CURLPROTO_HTTPS,CURLOPT_WRITEFUNCTION=>function($handle,$chunk)use(&$response){if(strlen($response)+strlen($chunk)>2097152)return 0;$response.=$chunk;return strlen($chunk);}];
        // Pin custom hosts to their validated resolution; prevent DNS rebinding.
        if($custom){$host=parse_url($url,PHP_URL_HOST);$records=dns_get_record($host,DNS_A|DNS_AAAA);$ip=$records[0]['ip']??$records[0]['ipv6']??'';if(!filter_var($ip,FILTER_VALIDATE_IP,FILTER_FLAG_NO_PRIV_RANGE|FILTER_FLAG_NO_RES_RANGE))throw new HttpError(422,'Invalid webhook host.');$options[CURLOPT_RESOLVE]=[$host.':443:'.(str_contains($ip,':')?'['.$ip.']':$ip)];}
        if($body!==null)$options[CURLOPT_POSTFIELDS]=json_encode($body,JSON_THROW_ON_ERROR);
        curl_setopt_array($curl,$options);$ok=curl_exec($curl);$status=(int)curl_getinfo($curl,CURLINFO_RESPONSE_CODE);curl_close($curl);
        if($ok===false||$status<200||$status>=300)throw new ProviderError($method==='POST'&&($ok===false||$status>=500));
        if($response==='')return [];try{$data=json_decode($response,true,64,JSON_THROW_ON_ERROR);}catch(\JsonException){if($custom)return [];throw new ProviderError($method==='POST');}if(!is_array($data)){if($custom)return [];throw new ProviderError($method==='POST');}return $data;
    }
}
