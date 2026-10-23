<?php
declare(strict_types=1);
namespace Annam;
final class Razorpay {
    public function __construct(private array $connection) {}
    public static function identifier(string $value,string $prefix): string {if(!preg_match('/^'.preg_quote($prefix,'/').'_[a-zA-Z0-9]{1,70}$/D',$value))throw new HttpError(422,'Invalid payment reference.');return $value;}
    public function request(string $method,string $path,?array $body=null,array $headers=[]): array {
        return Http::json($method,'https://api.razorpay.com/v1/'.$path,['Authorization'=>'Basic '.base64_encode($this->connection['key_id'].':'.Crypto::decrypt($this->connection['_key_secret']))]+$headers,$body);
    }
    public function payment(string $id): array {return $this->request('GET','payments/'.self::identifier($id,'pay'));}
    public function order(string $id): array {return $this->request('GET','orders/'.self::identifier($id,'order'));}
    public function find(string $receipt): ?array {foreach($this->request('GET','orders?'.http_build_query(['receipt'=>$receipt,'count'=>100]))['items']??[] as $row)if(($row['receipt']??'')===$receipt)return $row;return null;}
}
