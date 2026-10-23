<?php
declare(strict_types=1);
namespace Annam;
final class MessagePayload {
    public static function graph(string $phone,array $p): array {
        $base=['messaging_product'=>'whatsapp','to'=>$phone];$kind=$p['kind']??'';
        if($kind!=='template'&&$kind!=='document'){if(!is_string($p['body']??null)||trim($p['body'])===''||mb_strlen($p['body'])>1024)throw new HttpError(422,'Messages need 1 to 1,024 characters.');}
        if($kind==='text')return $base+['type'=>'text','text'=>['body'=>$p['body']]];
        if($kind==='template'){if(!preg_match('/^[a-z0-9_]{1,512}$/D',$p['name']??'')||!preg_match('/^[a-zA-Z_]{2,10}$/D',$p['language']??'en')||count($p['params']??[])>30)throw new HttpError(422,'Check the approved template name and language.');$template=['name'=>$p['name'],'language'=>['code'=>$p['language']??'en']];if($p['params']??[])$template['components']=[['type'=>'body','parameters'=>array_map(fn($v)=>['type'=>'text','text'=>(string)$v],$p['params'])]];return $base+['type'=>'template','template'=>$template];}
        if($kind==='document'){self::url($p['url']??'');return $base+['type'=>'document','document'=>['link'=>$p['url'],'filename'=>mb_substr((string)($p['filename']??'document.pdf'),0,200),'caption'=>mb_substr((string)($p['caption']??''),0,1024)]];}
        $interactive=['body'=>['text'=>$p['body']]];
        if($kind==='buttons'){$options=$p['buttons']??[];if(count($options)<1||count($options)>3)throw new HttpError(422,'Choose one to three buttons.');foreach($options as $b)if(!is_string($b['id']??null)||strlen($b['id'])>256||!trim($b['title']??'')||mb_strlen($b['title'])>20)throw new HttpError(422,'Button labels are limited to 20 characters.');$interactive+=['type'=>'button','action'=>['buttons'=>array_map(fn($b)=>['type'=>'reply','reply'=>$b],$options)]];}
        elseif($kind==='cta_url'){self::url($p['url']??'');if(!trim($p['label']??'')||mb_strlen($p['label'])>20)throw new HttpError(422,'Link labels are limited to 20 characters.');$interactive+=['type'=>'cta_url','action'=>['name'=>'cta_url','parameters'=>['display_text'=>$p['label'],'url'=>$p['url']]]];}
        elseif($kind==='list'){$sections=$p['sections']??[];$count=0;foreach($sections as $section)foreach($section['rows']??[] as $row){$count++;if(!trim($row['title']??'')||mb_strlen($row['title'])>24||strlen($row['id']??'')>200||mb_strlen($row['description']??'')>72)throw new HttpError(422,'Check list row labels.');}if($count<1||$count>10||!trim($p['button']??'')||mb_strlen($p['button'])>20)throw new HttpError(422,'Lists support up to ten rows and a 20-character button label.');$interactive+=['type'=>'list','action'=>['button'=>$p['button'],'sections'=>$sections]];}
        else throw new HttpError(422,'Unsupported message type.');return $base+['type'=>'interactive','interactive'=>$interactive];
    }
    private static function url(string $url): void {if(!filter_var($url,FILTER_VALIDATE_URL)||parse_url($url,PHP_URL_SCHEME)!=='https'||parse_url($url,PHP_URL_USER)!==null)throw new HttpError(422,'Use a valid HTTPS link.');}
    public static function body(array $message): string {
        $type=$message['type']??'text';return match($type){'text'=>(string)($message['text']['body']??''),'interactive'=>(string)($message['interactive']['button_reply']['title']??$message['interactive']['list_reply']['title']??'Interactive reply'),'button'=>(string)($message['button']['text']??''),'image','document','audio','video','sticker'=>(string)($message[$type]['caption']??$message[$type]['filename']??ucfirst($type)),'location'=>'Location: '.($message['location']['name']??'').' '.($message['location']['address']??''),'order'=>'Customer shared a catalog order','reaction'=>(string)($message['reaction']['emoji']??'Reaction'),'contacts'=>'Shared contact',default=>ucfirst((string)$type)};
    }
}
