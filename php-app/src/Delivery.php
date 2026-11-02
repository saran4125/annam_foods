<?php
declare(strict_types=1);
namespace Annam;

final class Delivery {
    public const DINNER='Dinner cannot be combined with other food categories. Please place a separate order for Dinner.';
    public const BREAKFAST='Breakfast delivery is not available for your pincode.';
    public const BREAKFAST_DINNER='Breakfast and Dinner delivery services are not available for your pincode.';
    public const SNACKS_ONLY='Only Snacks delivery is available for your pincode. Breakfast, Lunch, and Dinner delivery services are not available.';
    public const COURIER='Please note that courier charges are not included in the current order amount. The applicable courier charges will be confirmed after your order has been dispatched, and you will be required to pay the courier charges separately after dispatch.';
    public function __construct(private Store $store){}
    public static function combination(array $keys):void {
        $keys=array_unique($keys);if(in_array('dinner',$keys,true)&&count($keys)>1)throw new HttpError(422,self::DINNER);
    }
    public static function slotOpen(array $slot,string $date,?\DateTimeImmutable $now=null):bool {
        $now??=new \DateTimeImmutable();$today=$now->format('Y-m-d');
        if(!$slot['active']||!in_array($date,[$today,$now->modify('+1 day')->format('Y-m-d')],true))return false;
        $opens=(new \DateTimeImmutable($date.' '.($slot['order_opens_at']??'00:00:00')))->modify('-'.(int)($slot['order_days_before']??1).' days');
        return $now>=$opens&&$now<new \DateTimeImmutable($date.' '.$slot['order_cutoff']);
    }
    public function restriction(string $pin,array $keys,?int $area=null):string {
        $zones=$this->store->db->rows('SELECT * FROM delivery_deliveryzone WHERE tenant_id=? AND pincode=? AND active'.($area?' AND id=?':''),$area?[$this->store->id(),$pin,$area]:[$this->store->id(),$pin]);
        if(!$zones)return "We don't deliver meals to this pincode.";
        $allowed=[];foreach($zones as $z)$allowed=array_unique([...$allowed,...(json_decode($z['slot_keys'],true)?:['breakfast','lunch','dinner','snacks'])]);
        $missing=array_diff($keys,$allowed);if(!$missing)return '';
        if($allowed===['snacks'])return self::SNACKS_ONLY;
        if(!array_intersect(['breakfast','dinner'],$allowed)&&array_intersect(['breakfast','dinner'],$missing))return self::BREAKFAST_DINNER;
        if(in_array('breakfast',$missing,true))return self::BREAKFAST;
        return in_array('dinner',$missing,true)?'Dinner delivery is not available for your pincode.':'This food category is not available for your pincode.';
    }
    public function local(string $pin,array $keys,int $subtotal,?int $area=null):array {
        self::combination($keys);if(!preg_match('/^[1-9][0-9]{5}$/D',$pin))throw new HttpError(422,'Enter a valid six-digit pincode.');
        if($message=$this->restriction($pin,$keys,$area))throw new HttpError(422,$message);
        $zones=$this->store->db->rows('SELECT * FROM delivery_deliveryzone WHERE tenant_id=? AND active AND pincode=? ORDER BY area_name',[$this->store->id(),$pin]);
        $zones=array_values(array_filter($zones,fn($z)=>!array_diff($keys,json_decode($z['slot_keys'],true)?:['breakfast','lunch','dinner','snacks'])));
        $zone=null;if($area){foreach($zones as $z)if((int)$z['id']===$area)$zone=$z;}elseif(count($zones)===1)$zone=$zones[0];
        if(!$zone)throw new HttpError(422,'Choose your delivery area, then review your order again.');
        $minimum=Money::parse($zone['min_order']);if($subtotal<$minimum)throw new HttpError(422,'Minimum food value is '.Money::display($minimum).'. Add '.Money::display($minimum-$subtotal).' more.');
        return ['zone'=>$zone,'fee'=>Money::parse($zone['delivery_fee']),'minimum'=>$minimum,'deferred'=>false];
    }
    public function snacks(array $details,int $subtotal):array {
        $cfg=$this->store->config['checkout_settings'];Settings::validateCheckout($cfg);
        if(!($cfg['courier_enabled']??false))throw new HttpError(422,'Shop delivery is currently unavailable. Please contact the kitchen.');
        $country=$details['country']??'India';$pin=$details['pincode']??'';
        if(strcasecmp($country,'India')===0&&$this->store->db->one('SELECT id FROM delivery_deliveryzone WHERE tenant_id=? AND pincode=? AND active',[$this->store->id(),$pin]))return $this->local($pin,['snacks'],$subtotal,$details['zone_id']??null);
        if(strcasecmp($country,'India')===0&&in_array(strtolower(trim($details['city']??'')),['chennai','madras'],true))throw new HttpError(422,'Enter an approved Chennai delivery pincode and choose your area.');
        $minimum=Money::parse((string)($cfg['courier_minimum']??'0'));if($subtotal<$minimum)throw new HttpError(422,'Minimum shop items value is '.Money::display($minimum).'.');
        return ['zone'=>['area_name'=>'Courier delivery — charge payable after dispatch','delivery_fee'=>'0.00','min_order'=>Money::decimal($minimum)],'fee'=>0,'minimum'=>$minimum,'deferred'=>true];
    }
}
