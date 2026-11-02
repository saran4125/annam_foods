<?php
declare(strict_types=1);
namespace Annam;

final class Orders {
    public const FLOW=['placed'=>['confirmed'],'confirmed'=>['preparing'],'preparing'=>['out_for_delivery'],'out_for_delivery'=>['delivered'],'delivered'=>[],'cancelled'=>[]];
    public function __construct(private Store $store) {}
    public function get(int $id,bool $lock=false): array {
        return Store::json($this->store->row('orders_order',$id,$lock),['items','address','pricing','buyer_gst']);
    }
    public function all(?string $channel=null,string $query=''): array {
        $sql='SELECT o.*,c.name AS customer_name,c.phone AS customer_phone FROM orders_order o JOIN orders_customer c ON c.id=o.customer_id AND c.tenant_id=o.tenant_id WHERE o.tenant_id=?';$params=[$this->store->id()];
        if($channel&&in_array($channel,['web','manual','whatsapp'],true)){$sql.=' AND o.channel=?';$params[]=$channel;}
        if($query!==''){$sql.=' AND (o.order_no ILIKE ? OR c.name ILIKE ? OR c.phone ILIKE ?)';array_push($params,'%'.$query.'%','%'.$query.'%','%'.$query.'%');}
        return $this->store->db->rows($sql.' ORDER BY o.placed_at DESC LIMIT 500',$params);
    }
    public static function phone(string $value,string $country='India'):string {
        $digits=preg_replace('/[\s()+-]/','',$value);if(!preg_match('/^[0-9]{10,15}$/D',$digits))throw new HttpError(422,'Enter a phone number with 10 to 15 digits.');
        return strlen($digits)===10&&strcasecmp($country,'India')===0?'91'.$digits:$digits;
    }
    private function customer(array $details,string $channel): array {
        $db=$this->store->db;$now=date('c');
        $variants=CustomerLookup::variants($details['phone']);$customer=$db->one('SELECT * FROM orders_customer WHERE tenant_id=? AND phone IN ('.implode(',',array_fill(0,count($variants),'?')).') ORDER BY last_seen DESC,id DESC LIMIT 1 FOR UPDATE',[$this->store->id(),...$variants]);
        if($customer){$values=['last_seen'=>$now];if(!$customer['name'])$values['name']=$details['name'];if(!$customer['email']&&!empty($details['email']))$values['email']=$details['email'];$this->store->update('orders_customer',$customer['id'],$values);return $customer;}
        return $this->store->insert('orders_customer',['phone'=>$details['phone'],'name'=>$details['name'],'email'=>$details['email']??'','gstin'=>'','business_name'=>'','billing_address'=>'','source'=>$channel,'first_seen'=>$now,'last_seen'=>$now,'notes'=>'']);
    }
    public function create(array $quote,array $details,string $external,string $channel='web',string $actor='customer:web'): array {
        return $this->store->db->transaction(function()use($quote,$details,$external,$channel,$actor){
            $this->store->lock();
            if(!in_array($channel,['web','manual','whatsapp'],true)||!in_array($details['payment_method'],['online','manual','cod'],true))throw new HttpError(422,'Invalid order channel or payment method.');
            $existing=$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND external_ref=?',[$this->store->id(),$external]);if($existing)return $this->get((int)$existing['id']);
            if($channel==='web'&&!empty($quote['date']))foreach($quote['lines'] as $line){
                if(($line['meal_key']??'snacks')==='snacks')continue;
                $slot=$this->store->db->one('SELECT id FROM catalog_slot WHERE tenant_id=? AND key=?',[$this->store->id(),$line['meal_key']]);
                $menu=$this->store->menu($quote['date'],(int)$slot['id']);$match=null;foreach($menu as $row)if((int)$row['id']===(int)$line['item_id'])$match=$row;
                if(!$match)throw new HttpError(409,'A dish is no longer available. Review your cart.');
                $reserved=$this->store->db->one('UPDATE catalog_menuschedule SET qty_sold=qty_sold+? WHERE tenant_id=? AND id=? AND (qty_limit IS NULL OR qty_sold+?<=qty_limit) RETURNING id',[(int)$line['quantity'],$this->store->id(),$match['schedule_id'],(int)$line['quantity']]);
                if(!$reserved)throw new HttpError(409,'A dish has sold out. Review your cart.');
            }
            $customer=$this->customer($details,$channel);$number='';
            for($i=0;$i<10;$i++){$number=strtoupper(substr($this->store->tenant['slug'],0,8)).'-'.date('Ymd').'-'.random_int(1000,9999);if(!$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND order_no=?',[$this->store->id(),$number]))break;}
            $address=array_intersect_key($details,array_flip(['line1','line2','landmark','pincode','city','state','country','zone_id']));
            $address+=['recipient_name'=>$details['name'],'phone'=>$details['phone'],'email'=>$details['email']??'','area'=>$quote['zone']['area_name']??'','state'=>'Tamil Nadu','country'=>'India','state_code'=>CustomerLookup::stateCode($details['country']??'India',$details['state']??'Tamil Nadu')];
            $address['courier_deferred']=$quote['courier_deferred']??false;
            if(!empty($details['collection']))$address['fulfilment']='Collection';
            $row=$this->store->insert('orders_order',['order_no'=>$number,'customer_id'=>$customer['id'],'channel'=>$channel,'source'=>$channel==='web'?'storefront':($channel==='whatsapp'?'wa_chat':'owner'),'payment_mode'=>$details['payment_method'],'fulfilment'=>$quote['kind'],'external_ref'=>$external,'payment_reference'=>'','buyer_gst'=>'{}','pricing'=>json_encode($quote['pricing'],JSON_THROW_ON_ERROR),'rider_name'=>'','rider_phone'=>'','status'=>'placed','payment_status'=>$details['payment_method']==='cod'?'cod_pending':'pending','slot_id'=>$quote['slot']['id']??null,'delivery_date'=>$quote['date']??null,'items'=>json_encode($quote['lines'],JSON_THROW_ON_ERROR),'address'=>json_encode($address,JSON_THROW_ON_ERROR),'subtotal'=>Money::decimal($quote['subtotal']),'delivery_fee'=>Money::decimal($quote['delivery_fee']),'discount'=>'0.00','total'=>Money::decimal($quote['total']),'coupon_code'=>'','placed_at'=>date('c'),'cancelled_reason'=>'']);
            $this->event((int)$row['id'],'','placed',$actor,'Order placed.');$saved=$this->get((int)$row['id']);if($address['courier_deferred'])(new Courier($this->store))->prepare($saved);return $saved;
        });
    }
    public function event(int $id,string $from,string $to,string $actor,string $note=''): void {
        $this->store->insert('orders_orderevent',['order_id'=>$id,'from_status'=>$from,'to_status'=>$to,'actor'=>substr($actor,0,60),'note'=>mb_substr($note,0,200),'at'=>date('c')]);
    }
    public function advance(int $id,string $next,string $actor,string $note='',array $rider=[]): array {
        return $this->store->db->transaction(function()use($id,$next,$actor,$note,$rider){
            $order=$this->get($id,true);$current=$order['status'];if($current===$next)return $order;
            if(in_array($current,['delivered','cancelled'],true)||($next!=='cancelled'&&!in_array($next,self::FLOW[$current]??[],true)))throw new HttpError(422,'This order cannot move to that status.');
            $values=['status'=>$next];if($next==='cancelled')$values['cancelled_reason']=mb_substr($note,0,200);
            if($next==='out_for_delivery'){$values['rider_name']=mb_substr((string)($rider['name']??''),0,120);$values['rider_phone']=mb_substr((string)($rider['phone']??''),0,20);}
            $this->store->update('orders_order',$id,$values);$this->event($id,$current,$next,$actor,$note);
            $order=$this->get($id);$this->notify($order,$next);
            if($next==='delivered'&&$order['payment_status']==='paid'&&(new Billing($this->store))->timing()==='on_delivery') (new Billing($this->store))->tryIssue($id);
            return $order;
        });
    }
    public function confirm(int $id,string $actor,string $reference,bool $confirmed): array {
        if(!$confirmed)throw new HttpError(422,'Confirm that the payment has actually been received.');
        $result=$this->store->db->transaction(function()use($id,$actor,$reference){
            $order=$this->get($id,true);
            if($this->store->db->one('SELECT id FROM payments_paymentintent WHERE tenant_id=? AND order_id=?',[$this->store->id(),$id]))throw new HttpError(422,'This payment must be verified through Razorpay.');
            if(in_array($order['status'],['cancelled'],true)||$order['payment_status']==='refunded')throw new HttpError(422,'Cancelled or refunded orders cannot be marked paid.');
            if($order['payment_status']!=='paid'){$this->store->update('orders_order',$id,['payment_status'=>'paid','payment_reference'=>mb_substr($reference,0,120)]);$this->event($id,$order['status'],$order['status'],$actor,'Payment receipt confirmed.');}
            return $this->get($id);
        });
        if((new Billing($this->store))->timing()==='on_payment') (new Billing($this->store))->tryIssue($id);
        return $result;
    }
    public function staff(array $input,string $actor):array {return (new StaffBooking($this->store))->create($input,$actor);}
    private function notify(array $order,string $status): void {
        $flags=$this->store->config['features'];if(!($flags['notify_'.$status]??false))return;
        (new Messaging($this->store))->queue($order['address']['phone']??'',['kind'=>'text','body'=>'Your Annam Foods order '.$order['order_no'].' is '.str_replace('_',' ',$status).'.'],'order_'.$status,'order:'.$order['id'].':'.$status);
    }
}
