<?php
declare(strict_types=1);
namespace Annam;

final class CustomerLookup {
    public function __construct(private Store $store){}
    public static function stateCode(string $country,string $state):string {
        if(strcasecmp($country,'India')!==0)return '96';$codes=json_decode(file_get_contents(ANNAM_ROOT.'/resources/state-codes.json'),true,64,JSON_THROW_ON_ERROR);
        return $codes[preg_replace('/\s+/','',strtolower($state))]??'';
    }
    public static function variants(string $digits):array {
        $variants=[$digits,'+'.$digits];if(strlen($digits)===10)array_push($variants,'91'.$digits,'+91'.$digits);elseif(strlen($digits)===12&&str_starts_with($digits,'91'))$variants[]=substr($digits,2);return array_values(array_unique($variants));
    }
    public function find(string $phone):array {
        $digits=preg_replace('/[\s()+-]/','',$phone);if(!preg_match('/^[0-9]{10,15}$/D',$digits))throw new HttpError(422,'Enter a phone number with 10 to 15 digits.');
        $variants=self::variants($digits);
        $customers=$this->store->db->rows('SELECT id,name FROM orders_customer WHERE tenant_id=? AND phone IN ('.implode(',',array_fill(0,count($variants),'?')).') ORDER BY last_seen DESC',[$this->store->id(),...$variants]);if(!$customers)return ['found'=>false];
        $ids=array_column($customers,'id');$params=[$this->store->id(),...$ids];$sql="SELECT o.address,c.name FROM orders_order o JOIN orders_customer c ON c.id=o.customer_id AND c.tenant_id=o.tenant_id WHERE o.tenant_id=? AND o.customer_id IN (".implode(',',array_fill(0,count($ids),'?')).") AND o.status<>'cancelled'";
        $latest=$this->store->db->one($sql.' ORDER BY o.placed_at DESC,o.id DESC LIMIT 1',$params);$delivery=$this->store->db->one($sql." AND COALESCE(o.address->>'line1','')<>'' ORDER BY o.placed_at DESC,o.id DESC LIMIT 1",$params);
        $last=$latest?json_decode($latest['address'],true):[];$snapshot=$delivery?json_decode($delivery['address'],true):[];
        if(!$snapshot){$saved=$this->store->db->one('SELECT a.*,z.area_name AS area FROM orders_address a LEFT JOIN delivery_deliveryzone z ON z.id=a.zone_id AND z.tenant_id=a.tenant_id WHERE a.tenant_id=? AND a.customer_id IN ('.implode(',',array_fill(0,count($ids),'?')).') ORDER BY a.is_default DESC,a.id LIMIT 1',$params);$snapshot=$saved?:[];}
        $zone=null;if(!empty($snapshot['pincode'])&&empty($snapshot['courier_deferred'])){$zones=$this->store->db->rows('SELECT id,area_name FROM delivery_deliveryzone WHERE tenant_id=? AND pincode=? AND active',[$this->store->id(),$snapshot['pincode']]);foreach($zones as $candidate)if(($snapshot['area']??'')===$candidate['area_name'])$zone=$candidate;if(!$zone&&empty($snapshot['area'])&&count($zones)===1)$zone=$zones[0];}
        return ['found'=>true,'details'=>['name'=>$last['recipient_name']??$latest['name']??$customers[0]['name'],'address'=>implode("\n",array_filter([$snapshot['line1']??'',$snapshot['line2']??'',$snapshot['landmark']??''])),'city'=>$snapshot['city']??'','state'=>$snapshot['state']??'Tamil Nadu','country'=>$snapshot['country']??'India','postal_code'=>$snapshot['pincode']??'','zone'=>(string)($zone['id']??''),'fulfilment_method'=>!empty($snapshot['courier_deferred'])?'courier':''],'needs_area_selection'=>!empty($snapshot['pincode'])&&!$zone&&empty($snapshot['courier_deferred'])];
    }
}
