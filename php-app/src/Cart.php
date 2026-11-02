<?php
declare(strict_types=1);
namespace Annam;

final class Cart {
    public static function keys(array $cart):array {
        $keys=[];foreach($cart['lines']??[] as $key=>$quantity)$keys[]=$cart['line_slots'][$key]??($cart['kind']==='courier'?'snacks':(string)($cart['slot_key']??''));
        return array_values(array_unique(array_filter($keys)));
    }
    public static function itemId(int|string $key):int {return (int)substr((string)$key,(int)(strrpos((string)$key,':')!==false?strrpos((string)$key,':')+1:0));}
    public static function add(Store $store,array $input):void {
        $id=filter_var($input['item_id']??'',FILTER_VALIDATE_INT);$quantity=filter_var($input['quantity']??'1',FILTER_VALIDATE_INT);
        if(!$id||!$quantity||$quantity<1||$quantity>99)throw new HttpError(422,'Choose a quantity between 1 and 99.');
        $item=$store->item($id);if(!$item['active']||!($item['in_stock']??true))throw new HttpError(422,'This item is unavailable.');
        if(!($store->config['features']['website_ordering']??true))throw new HttpError(422,'Website ordering is closed.');
        if($item['fulfilment']==='courier'&&!($store->config['features']['snacks_courier']??false))throw new HttpError(422,'Shop ordering is closed.');
        $slot=$item['fulfilment']==='scheduled'?$store->slot((int)($input['slot_id']??0)):null;
        $date=$slot?Store::date($input['date']??''):null;$meal=$slot['key']??'snacks';
        $cart=$_SESSION['cart']??['kind'=>$item['fulfilment'],'date'=>$date,'slot_id'=>$slot['id']??null,'slot_key'=>$meal,'lines'=>[],'line_slots'=>[]];
        if($cart['kind']==='courier'&&$slot)throw new HttpError(422,'Start a meals cart before adding Snacks, or place separate orders.');
        if($slot&&$cart['date']!==$date)throw new HttpError(422,'Different delivery dates require separate orders.');
        $current=self::keys($cart);if(!$current&&$cart['kind']==='scheduled'&&!empty($cart['slot_id']))$current=[$store->slot((int)$cart['slot_id'])['key']];
        Delivery::combination([...$current,$meal]);
        if(!empty($cart['pincode'])&&($message=(new Delivery($store))->restriction($cart['pincode'],[...$current,$meal],$cart['zone_id']??null)))throw new HttpError(422,$message);
        $key=(string)$id;if(isset($cart['lines'][$key])&&($cart['line_slots'][$key]??$cart['slot_key']??$meal)!==$meal)$key=$meal.':'.$id;
        $next=($cart['lines'][$key]??0)+$quantity;if($next>99)throw new HttpError(422,'Maximum quantity is 99 per item.');
        if($slot)self::scheduledItem($store,$id,$date,(int)$slot['id'],$next);
        $cart['lines'][$key]=$next;$cart['line_slots'][$key]=$meal;$_SESSION['cart']=$cart;
    }
    public static function set(Store $store,int|string $key,int $quantity):void {
        $cart=$_SESSION['cart']??['lines'=>[]];if(!isset($cart['lines'][$key]))throw new HttpError(404,'Cart item not found.');
        if($quantity<0||$quantity>99)throw new HttpError(422,'Choose a quantity from 0 to 99.');
        if(!$quantity)unset($cart['lines'][$key]);else $cart['lines'][$key]=$quantity;self::quote($store,$cart);$_SESSION['cart']=$cart;
    }
    private static function scheduledItem(Store $store,int $id,string $date,int $slotId,int $quantity):array {
        $slot=$store->slot($slotId);if(!Delivery::slotOpen($slot,$date))throw new HttpError(422,'Ordering is not open for this meal on the selected date.');
        if(in_array($date,$store->config['checkout_settings']['closed_dates']??[],true))throw new HttpError(422,'The kitchen is closed on this date.');
        foreach($store->menu($date,$slotId) as $entry)if((int)$entry['id']===$id){if($entry['qty_limit']!==null&&$quantity>$entry['qty_limit']-$entry['qty_sold'])throw new HttpError(422,'Not enough portions are available.');return $entry;}
        throw new HttpError(422,'This dish is not available for the selected meal and date.');
    }
    public static function quote(Store $store,?array $cart=null):array {
        $cart??=$_SESSION['cart']??['lines'=>[]];$lines=[];$subtotal=0;$keys=[];
        foreach($cart['lines'] as $key=>$quantity){
            if(!is_int($quantity)||$quantity<1||$quantity>99)throw new HttpError(422,'Invalid cart quantity.');
            $id=self::itemId($key);$item=$store->item($id);if(!$item['active']||!($item['in_stock']??true))throw new HttpError(422,'A cart item is no longer available. Remove it before proceeding.');
            $meal=$cart['line_slots'][$key]??($item['fulfilment']==='courier'?'snacks':$store->slot((int)$cart['slot_id'])['key']);
            if($cart['kind']==='courier'&&$item['fulfilment']!=='courier')throw new HttpError(422,'Invalid shop cart.');
            $price=$item['price'];if($item['fulfilment']==='scheduled'){$slot=$store->db->one('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?',[$store->id(),$meal])??throw new HttpError(422,'Choose a valid meal.');$price=self::scheduledItem($store,$id,$cart['date'],(int)$slot['id'],$quantity)['effective_price'];}
            $unit=Money::parse($price);$amount=$unit*$quantity;$keys[]=$meal;
            $lines[]=['item'=>$item,'quantity'=>$quantity,'unit'=>$unit,'amount'=>$amount,'meal_key'=>$meal,'meal_label'=>ucfirst($meal),'key'=>$key];$subtotal+=$amount;
        }
        Delivery::combination($keys);return ['lines'=>$lines,'subtotal'=>$subtotal,'cart'=>$cart,'meal_keys'=>array_values(array_unique($keys))];
    }
}
