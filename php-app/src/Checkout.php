<?php
declare(strict_types=1);
namespace Annam;

final class Checkout {
    public function __construct(private Store $store) {}
    public function details(array $input): array {
        $result=[];foreach(['name'=>120,'email'=>254,'line1'=>200,'line2'=>200,'city'=>80,'landmark'=>120] as $key=>$limit){$value=$input[$key]??'';if(!is_string($value)||mb_strlen(trim($value))>$limit)throw new HttpError(422,'Check '.$key.'.');$result[$key]=trim($value);}
        foreach(['name','line1','city'] as $key)if($result[$key]==='')throw new HttpError(422,'Enter '.$key.'.');
        if($result['email']!==''&&!filter_var($result['email'],FILTER_VALIDATE_EMAIL))throw new HttpError(422,'Enter a valid email address.');
        $result['phone']=Orders::phone((string)($input['phone']??''));$result['pincode']=trim((string)($input['pincode']??''));
        if(!preg_match('/^[1-9][0-9]{5}$/D',$result['pincode']))throw new HttpError(422,'Enter an exact six-digit pincode.');
        $result['zone_id']=empty($input['zone_id'])?null:(int)$input['zone_id'];$result['payment_method']=(string)($input['payment_method']??'manual');
        if(!isset($this->choices()[$result['payment_method']]))throw new HttpError(422,'Choose an available payment method.');return $result;
    }
    public function choices(): array {
        $result=[];$features=$this->store->config['features'];
        if($this->store->db->one('SELECT id FROM payments_razorpayconnection WHERE tenant_id=? AND enabled',[$this->store->id()]))$result['online']='Pay online with Razorpay';
        if($features['cod']??false)$result['cod']='Cash on delivery';
        if($features['manual_payments']??true)$result['manual']='Arrange payment with the kitchen';return $result;
    }
    public function quote(array $cart,array $details): array {
        if(!($this->store->config['features']['website_ordering']??true))throw new HttpError(422,'Website ordering is currently closed.');
        $live=Cart::quote($this->store,$cart);if(!$live['lines'])throw new HttpError(422,'Add items before checking out.');
        $lines=[];foreach($live['lines'] as $line)$lines[]=Pricing::line($line['item'],$line['quantity'],Money::decimal($line['unit']));
        $slot=null;$date=null;
        if($cart['kind']==='courier'){
            if(!($this->store->config['features']['snacks_courier']??false))throw new HttpError(422,'Shop ordering is unavailable.');
            $cfg=$this->store->config['checkout_settings'];Settings::validateCheckout($cfg);
            if(!($cfg['courier_enabled']??false)||!in_array($details['pincode'],$cfg['courier_pincodes']??[],true))throw new HttpError(422,'We do not ship shop items to this pincode.');
            $minimum=Money::parse((string)$cfg['courier_minimum']);if($live['subtotal']<$minimum)throw new HttpError(422,'Minimum shop items value is '.Money::display($minimum).'.');
            $zone=['area_name'=>'Tamil Nadu courier delivery','delivery_fee'=>$cfg['courier_fee'],'min_order'=>$cfg['courier_minimum']];$fee=Money::parse((string)$cfg['courier_fee']);
        }else{
            if(!in_array($cart['date'],[date('Y-m-d'),date('Y-m-d',strtotime('+1 day'))],true))throw new HttpError(422,'Choose today or tomorrow for meal delivery.');
            $slot=$this->store->slot((int)$cart['slot_id']);$date=$cart['date'];if(in_array($date,$this->store->config['checkout_settings']['closed_dates']??[],true))throw new HttpError(422,'Meals are closed on this date.');$closed=$this->store->config['kitchen_closed_window']??[];
            if(isset($closed['from'],$closed['to'])&&$date>=$closed['from']&&$date<=$closed['to'])throw new HttpError(422,'The kitchen is closed on this date.');
            $delivery=$this->store->zoneQuote($details['pincode'],$slot['key'],$live['subtotal'],$details['zone_id']);$zone=$delivery['zone'];$fee=$delivery['fee'];
        }
        $quote=Pricing::totals($lines,$fee,$this->store->profile())+['zone'=>$zone,'kind'=>$cart['kind'],'slot'=>$slot,'date'=>$date];
        $connection=$details['payment_method']==='online'?$this->store->db->one('SELECT id,key_id,mode FROM payments_razorpayconnection WHERE tenant_id=? AND enabled',[$this->store->id()]):null;
        if($details['payment_method']==='online'&&!$connection)throw new HttpError(422,'Online payments are unavailable.');
        $quote['connection']=$connection;return $quote;
    }
    public static function fingerprint(array $quote,array $details): string { return hash('sha256',json_encode([$quote,$details],JSON_THROW_ON_ERROR)); }
    public function review(array $input): array {
        $this->store->reload();$details=$this->details($input);$cart=$_SESSION['cart']??[];$quote=$this->quote($cart,$details);
        $reference=str_replace('-','',Store::uuid());$_SESSION['checkout_browser']??=bin2hex(random_bytes(16));
        $_SESSION['checkout_reviews'][$reference]=['details'=>$details,'cart'=>$cart,'fingerprint'=>self::fingerprint($quote,$details),'expires'=>time()+1800];
        foreach($_SESSION['checkout_reviews'] as $key=>$record)if($record['expires']<time())unset($_SESSION['checkout_reviews'][$key]);
        if(count($_SESSION['checkout_reviews'])>20)$_SESSION['checkout_reviews']=array_slice($_SESSION['checkout_reviews'],-20,null,true);
        return ['reference'=>$reference,'quote'=>$quote,'details'=>$details];
    }
    public function place(string $reference): array {
        if(!preg_match('/^[a-f0-9]{32}$/D',$reference)||empty($_SESSION['checkout_browser']))throw new HttpError(422,'The checkout review expired.');
        $external='web:'.$_SESSION['checkout_browser'].':'.$reference;
        return $this->store->db->transaction(function()use($reference,$external){
            $this->store->lock();$existing=$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND external_ref=?',[$this->store->id(),$external]);
            if($existing)return (new Orders($this->store))->get((int)$existing['id']);
            $review=$_SESSION['checkout_reviews'][$reference]??null;if(!$review||$review['expires']<time())throw new HttpError(422,'Your order review expired. Review the cart again.');
            $this->store->reload();$details=$this->details($review['details']);
            foreach(array_keys($review['cart']['lines']) as $id)$this->store->db->one('SELECT id FROM catalog_menuitem WHERE tenant_id=? AND id=? FOR UPDATE',[$this->store->id(),(int)$id]);
            $quote=$this->quote($_SESSION['cart']??[], $details);
            if(!hash_equals($review['fingerprint'],self::fingerprint($quote,$details)))throw new HttpError(409,'Your cart, prices or delivery settings changed. Please review the total again.');
            $order=(new Orders($this->store))->create($quote,$details,$external);
            if($details['payment_method']==='online') (new Payments($this->store))->intent($order,$quote['connection']);
            unset($_SESSION['cart']);return $order;
        });
    }
    public function guest(string $reference): array {
        $ref=str_replace('-','',$reference);if(!preg_match('/^[a-f0-9]{32}$/D',$ref))throw new HttpError(404,'Order not found.');
        $keys=array_filter([$_SESSION['checkout_browser']??null,LegacySession::browser($this->store->id())]);
        foreach($keys as $key){$row=$this->store->db->one('SELECT id FROM orders_order WHERE tenant_id=? AND external_ref=?',[$this->store->id(),'web:'.$key.':'.$ref]);if($row)return (new Orders($this->store))->get((int)$row['id']);}
        throw new HttpError(404,'Order not found for this browser.');
    }
}
