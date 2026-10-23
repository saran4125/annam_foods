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
    public static function phone(string $value): string {
        if(!preg_match('/^\+?[0-9 ()-]+$/D',$value)) throw new HttpError(422,'Enter a valid Indian mobile number.');
        $digits=preg_replace('/\D/','',$value);if(strlen($digits)===12&&str_starts_with($digits,'91'))$digits=substr($digits,2);
        if(!preg_match('/^[6-9][0-9]{9}$/D',$digits)) throw new HttpError(422,'Enter a valid ten-digit Indian mobile number.');return '91'.$digits;
    }
    private function customer(array $details,string $channel): array {
        $db=$this->store->db;$now=date('c');
        $customer=$db->one('SELECT * FROM orders_customer WHERE tenant_id=? AND phone=? FOR UPDATE',[$this->store->id(),$details['phone']]);
        if($customer){$values=['last_seen'=>$now];if(!$customer['name'])$values['name']=$details['name'];if(!$customer['email']&&!empty($details['email']))$values['email']=$details['email'];$this->store->update('orders_customer',$customer['id'],$values);return $customer;}
        return $this->store->insert('orders_customer',['phone'=>$details['phone'],'name'=>$details['name'],'email'=>$details['email']??'','gstin'=>'','business_name'=>'','billing_address'=>'','source'=>$channel,'first_seen'=>$now,'last_seen'=>$now,'notes'=>'']);
    }
    public function create(array $quote,array $details,string $external,string $channel='web',string $actor='customer:web'): array {
        return $this->store->db->transaction(function()use($quote,$details,$external,$channel,$actor){
            $this->store->lock();
            if(!in_array($channel,['web','manual','whatsapp'],true)||!in_array($details['payment_method'],['online','manual','cod'],true))throw new HttpError(422,'Invalid order channel or payment method.');
            $existing=$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND external_ref=?',[$this->store->id(),$external]);if($existing)return $this->get((int)$existing['id']);
            $customer=$this->customer($details,$channel);$number='';
            for($i=0;$i<10;$i++){$number=strtoupper(substr($this->store->tenant['slug'],0,8)).'-'.date('Ymd').'-'.random_int(1000,9999);if(!$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND order_no=?',[$this->store->id(),$number]))break;}
            $address=array_intersect_key($details,array_flip(['line1','line2','landmark','pincode','city']));
            $address+=['recipient_name'=>$details['name'],'phone'=>$details['phone'],'email'=>$details['email']??'','area'=>$quote['zone']['area_name']??'','state'=>'Tamil Nadu','state_code'=>'33'];
            if(!empty($details['collection']))$address['fulfilment']='Collection';
            $row=$this->store->insert('orders_order',['order_no'=>$number,'customer_id'=>$customer['id'],'channel'=>$channel,'source'=>$channel==='web'?'storefront':($channel==='whatsapp'?'wa_chat':'owner'),'payment_mode'=>$details['payment_method'],'fulfilment'=>$quote['kind'],'external_ref'=>$external,'payment_reference'=>'','buyer_gst'=>'{}','pricing'=>json_encode($quote['pricing'],JSON_THROW_ON_ERROR),'rider_name'=>'','rider_phone'=>'','status'=>'placed','payment_status'=>$details['payment_method']==='cod'?'cod_pending':'pending','slot_id'=>$quote['slot']['id']??null,'delivery_date'=>$quote['date']??null,'items'=>json_encode($quote['lines'],JSON_THROW_ON_ERROR),'address'=>json_encode($address,JSON_THROW_ON_ERROR),'subtotal'=>Money::decimal($quote['subtotal']),'delivery_fee'=>Money::decimal($quote['delivery_fee']),'discount'=>'0.00','total'=>Money::decimal($quote['total']),'coupon_code'=>'','placed_at'=>date('c'),'cancelled_reason'=>'']);
            $this->event((int)$row['id'],'','placed',$actor,'Order placed.');return $this->get((int)$row['id']);
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
    public function staff(array $input,string $actor): array {
        $name=trim((string)($input['name']??''));if(!$name||mb_strlen($name)>120)throw new HttpError(422,'Enter the customer name.');
        $details=['name'=>$name,'phone'=>self::phone((string)($input['phone']??'')),'email'=>'','payment_method'=>$input['payment_method']??'manual','line1'=>trim((string)($input['address']??'')),'collection'=>empty($input['zone_id'])];
        if(!in_array($details['payment_method'],['manual','cod'],true))throw new HttpError(422,'Staff bookings use manual payment or cash on delivery.');
        if(mb_strlen($details['line1'])>2000)throw new HttpError(422,'Delivery address is too long.');
        $channel=$input['channel']??'manual';if(!in_array($channel,['manual','whatsapp'],true))throw new HttpError(422,'Choose a valid booking channel.');
        $token=$input['token']??'';if(!is_string($token)||!preg_match('/^[a-f0-9]{32}$/D',$token)||!isset($_SESSION['staff_tokens'][$token]))throw new HttpError(422,'Reload the booking form before submitting.');
        return $this->store->db->transaction(function()use($input,$actor,$details,$channel,$token){
            $this->store->lock();$existing=$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND external_ref=?',[$this->store->id(),'billing:'.$token]);if($existing)return $this->get((int)$existing['id']);
            $lines=[];$quantities=$input['quantities']??[];if(!is_array($quantities)||count($quantities)>500)throw new HttpError(422,'Choose valid items.');
            foreach($quantities as $id=>$raw){if(!ctype_digit((string)$id)||!is_scalar($raw))throw new HttpError(422,'Choose valid item quantities.');if($raw===''||$raw==='0')continue;$q=filter_var($raw,FILTER_VALIDATE_INT);if($q===false||$q<1||$q>999)throw new HttpError(422,'Enter quantities from 1 to 999.');$item=$this->store->item((int)$id);if(!$item['active'])throw new HttpError(422,'An item is unavailable.');$lines[]=Pricing::line($item,$q);}
            if(!$lines||count($lines)>50)throw new HttpError(422,'Choose 1 to 50 items.');$subtotal=array_sum(array_map(fn($l)=>Money::parse($l['line_total']),$lines));$fee=0;$zone=[];
            if(!empty($input['zone_id'])){$zone=$this->store->db->one('SELECT * FROM delivery_deliveryzone WHERE tenant_id=? AND id=? AND active',[$this->store->id(),(int)$input['zone_id']])??throw new HttpError(422,'Choose an active delivery area.');if(!$details['line1'])throw new HttpError(422,'Enter a delivery address.');if($subtotal<Money::parse($zone['min_order']))throw new HttpError(422,'This area requires a minimum food value of '.money($zone['min_order']).'.');$fee=Money::parse($zone['delivery_fee']);$details['pincode']=$zone['pincode'];}
            $quote=Pricing::totals($lines,$fee,$this->store->profile())+['zone'=>$zone,'kind'=>'scheduled','slot'=>null,'date'=>null];
            return $this->create($quote,$details,'billing:'.$token,$channel,$actor);
        });
    }
    private function notify(array $order,string $status): void {
        $flags=$this->store->config['features'];if(!($flags['notify_'.$status]??false))return;
        (new Messaging($this->store))->queue($order['address']['phone']??'',['kind'=>'text','body'=>'Your Annam Foods order '.$order['order_no'].' is '.str_replace('_',' ',$status).'.'],'order_'.$status,'order:'.$order['id'].':'.$status);
    }
}
