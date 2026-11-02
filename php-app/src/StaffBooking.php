<?php
declare(strict_types=1);
namespace Annam;

final class StaffBooking {
    public function __construct(private Store $store){}
    public function create(array $input,string $actor):array {
        $name=trim((string)($input['name']??''));if(!$name||mb_strlen($name)>120)throw new HttpError(422,'Enter the customer name.');
        $country=trim((string)($input['country']??'India'))?:'India';
        $details=['name'=>$name,'phone'=>Orders::phone((string)($input['phone']??''),$country),'email'=>'','payment_method'=>$input['payment_method']??'manual','line1'=>trim((string)($input['address']??'')),'country'=>$country,'state'=>trim((string)($input['state']??'Tamil Nadu')),'city'=>trim((string)($input['city']??'')),'pincode'=>trim((string)($input['postal_code']??'')),'zone_id'=>empty($input['zone_id'])?null:(int)$input['zone_id'],'collection'=>empty($input['zone_id'])&&($input['fulfilment_method']??'')!=='courier'];
        if(!in_array($details['payment_method'],['manual','cod'],true)||mb_strlen($details['line1'])>2000)throw new HttpError(422,'Check the payment method and address.');
        $channel=$input['channel']??'manual';if(!in_array($channel,['manual','whatsapp'],true))throw new HttpError(422,'Choose a valid booking channel.');
        $token=$input['token']??'';if(!is_string($token)||!preg_match('/^[a-f0-9]{32}$/D',$token)||!isset($_SESSION['staff_tokens'][$token]))throw new HttpError(422,'Reload the booking form before submitting.');
        return $this->store->db->transaction(function()use($input,$actor,$details,$channel,$token){
            $this->store->lock();$orders=new Orders($this->store);$existing=$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND external_ref=?',[$this->store->id(),'billing:'.$token]);if($existing)return $orders->get((int)$existing['id']);
            $lines=[];$keys=[];$quantities=$input['quantities']??[];if(!is_array($quantities)||count($quantities)>10000)throw new HttpError(422,'Choose valid items.');
            foreach($quantities as $id=>$raw){if(!ctype_digit((string)$id)||!is_scalar($raw))throw new HttpError(422,'Choose valid quantities.');if($raw===''||$raw==='0')continue;$q=filter_var($raw,FILTER_VALIDATE_INT);if($q===false||$q<1||$q>999)throw new HttpError(422,'Use quantities from 1 to 999.');$item=$this->store->item((int)$id);if(!$item['active']||!($item['in_stock']??true))throw new HttpError(422,'An item is unavailable.');
                $assigned=array_column($this->store->db->rows('SELECT DISTINCT s.key FROM catalog_menuschedule m JOIN catalog_slot s ON s.id=m.slot_id AND s.tenant_id=m.tenant_id WHERE m.tenant_id=? AND m.item_id=?',[$this->store->id(),$id]),'key');
                $meal=$input['meals'][$id]??($item['fulfilment']==='courier'?'snacks':(count($assigned)===1?$assigned[0]:'unclassified'));
                if(!in_array($meal,['breakfast','lunch','dinner','snacks','unclassified'],true)||($item['fulfilment']==='courier'&&$meal!=='snacks')||($item['fulfilment']==='scheduled'&&$assigned&&!in_array($meal,$assigned,true)))throw new HttpError(422,'Choose the correct food category for each item.');
                $line=Pricing::line($item,$q);$line['meal_key']=$meal;$line['meal_label']=ucfirst($meal);$lines[]=$line;if($meal!=='unclassified')$keys[]=$meal;
            }
            if(!$lines||count($lines)>50)throw new HttpError(422,'Choose 1 to 50 items.');Delivery::combination($keys);
            $subtotal=array_sum(array_map(fn($l)=>Money::parse($l['line_total']),$lines));$fee=0;$zone=[];$deferred=false;
            if(($input['fulfilment_method']??'')==='courier'){
                if(array_values(array_unique($keys))!==['snacks']||!$details['line1']||!$details['city'])throw new HttpError(422,'Courier orders require only Snacks, a delivery address and city.');
                $delivery=(new Delivery($this->store))->snacks($details,$subtotal);if(!$delivery['deferred'])throw new HttpError(422,'Select the approved local delivery area.');$deferred=true;$zone=$delivery['zone'];
            }elseif($details['zone_id']){
                if(!$details['line1']||in_array('unclassified',array_column($lines,'meal_key'),true))throw new HttpError(422,'Enter an address and food category for each meal.');
                $selected=$this->store->db->one('SELECT pincode FROM delivery_deliveryzone WHERE tenant_id=? AND id=? AND active',[$this->store->id(),$details['zone_id']])??throw new HttpError(422,'Choose an active delivery area.');$details['pincode']=$selected['pincode'];$delivery=(new Delivery($this->store))->local($details['pincode'],$keys,$subtotal,$details['zone_id']);$zone=$delivery['zone'];$fee=$delivery['fee'];
            }
            $slot=count(array_unique($keys))===1?$this->store->db->one('SELECT * FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$keys[0]]):null;
            $date=!empty($input['delivery_date'])?Store::date($input['delivery_date']):null;
            $quote=Pricing::totals($lines,$fee,$this->store->profile())+['zone'=>$zone,'kind'=>$deferred?'courier':'scheduled','slot'=>$slot,'date'=>$date,'courier_deferred'=>$deferred];
            return $orders->create($quote,$details,'billing:'.$token,$channel,$actor);
        });
    }
}
