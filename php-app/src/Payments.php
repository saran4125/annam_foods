<?php
declare(strict_types=1);
namespace Annam;

final class Payments {
    public function __construct(private Store $store) {}
    public function intent(array $order,array $connection): array {
        $existing=$this->store->db->one('SELECT * FROM payments_paymentintent WHERE tenant_id=? AND order_id=?',[$this->store->id(),$order['id']]);if($existing)return $existing;
        return $this->store->insert('payments_paymentintent',['id'=>Store::uuid(),'order_id'=>$order['id'],'connection_id'=>$connection['id'],'key_id'=>$connection['key_id'],'mode'=>$connection['mode'],'amount'=>Money::parse($order['total']),'currency'=>'INR','provider_order_id'=>'','payment_id'=>'','state'=>'new','refunded_amount'=>0,'credit_note_id'=>null,'bill_error'=>'','created_at'=>date('c'),'updated_at'=>date('c')]);
    }
    public function forOrder(int $orderId): ?array {return $this->store->db->one('SELECT * FROM payments_paymentintent WHERE tenant_id=? AND order_id=?',[$this->store->id(),$orderId]);}
    private function connection(array $intent): array {$row=$this->store->row('payments_razorpayconnection',$intent['connection_id']);if($row['key_id']!==$intent['key_id']||$row['mode']!==$intent['mode'])throw new HttpError(422,'The original payment credentials are required to reconcile this order.');return $row;}
    public function start(int $orderId): array {
        $intent=$this->store->db->transaction(function()use($orderId){$order=(new Orders($this->store))->get($orderId,true);if($order['status']==='cancelled')throw new HttpError(422,'This order is cancelled.');$row=$this->forOrder($orderId)??throw new HttpError(404,'Online payment not found.');$row=$this->store->row('payments_paymentintent',$row['id'],true);
            if($row['provider_order_id']||in_array($row['state'],['captured','refunded','part_refunded'],true))return $row;
            if($row['state']==='creating'&&strtotime($row['updated_at'])>time()-30)throw new HttpError(409,'Payment setup is in progress. Check again shortly.');
            $row['reconcile']=in_array($row['state'],['creating','uncertain'],true);$this->store->update('payments_paymentintent',$row['id'],['state'=>'creating','updated_at'=>date('c')]);return $row;});
        if($intent['provider_order_id'])return $intent;$receipt='sk_'.str_replace('-','',$intent['id']);$provider=new Razorpay($this->connection($intent));
        try{
            $evidence=($intent['reconcile']??false)?$provider->find($receipt):$provider->request('POST','orders',['amount'=>(int)$intent['amount'],'currency'=>'INR','receipt'=>$receipt,'notes'=>['seer_payment'=>str_replace('-','',$intent['id'])]]);
            if(!$evidence)throw new ProviderError(true);
            if(!is_int($evidence['amount']??null)||$evidence['amount']!==(int)$intent['amount']||($evidence['currency']??'')!=='INR'||($evidence['receipt']??'')!==$receipt)throw new ProviderError(true);
            $providerId=Razorpay::identifier((string)($evidence['id']??''),'order');
        }catch(ProviderError $error){$this->store->db->transaction(function()use($intent,$error){$row=$this->store->row('payments_paymentintent',$intent['id'],true);if(!$row['provider_order_id']&&$row['state']==='creating')$this->store->update('payments_paymentintent',$intent['id'],['state'=>$error->uncertain?'uncertain':'error','updated_at'=>date('c')]);});throw $error;}
        return $this->store->db->transaction(function()use($intent,$providerId){$row=$this->store->row('payments_paymentintent',$intent['id'],true);if($row['provider_order_id']&&$row['provider_order_id']!==$providerId)throw new HttpError(409,'Payment reference conflict.');$values=['provider_order_id'=>$providerId,'updated_at'=>date('c')];if(!in_array($row['state'],['captured','refunded','part_refunded'],true))$values['state']='ready';$this->store->update('payments_paymentintent',$intent['id'],$values);return $this->store->row('payments_paymentintent',$intent['id']);});
    }
    public function verify(int $orderId,array $input): array {
        $intent=$this->forOrder($orderId)??throw new HttpError(404,'Payment not found.');$connection=$this->connection($intent);
        $payment=Razorpay::identifier((string)($input['razorpay_payment_id']??''),'pay');$order=Razorpay::identifier((string)($input['razorpay_order_id']??''),'order');
        if($order!==$intent['provider_order_id']||!hash_equals(hash_hmac('sha256',$order.'|'.$payment,Crypto::decrypt($connection['_key_secret'])),(string)($input['razorpay_signature']??'')))throw new HttpError(403,'Payment signature could not be verified.');
        return $this->apply($intent['id'],(new Razorpay($connection))->payment($payment));
    }
    public function apply(string $id,array $payment): array {
        $intent=$this->store->db->transaction(function()use($id,$payment){$intent=$this->store->row('payments_paymentintent',$id,true);$order=(new Orders($this->store))->get((int)$intent['order_id'],true);
            $paymentId=Razorpay::identifier((string)($payment['id']??''),'pay');if(($payment['order_id']??'')!==$intent['provider_order_id']||!is_int($payment['amount']??null)||$payment['amount']!==(int)$intent['amount']||($payment['currency']??'')!==$intent['currency'])throw new HttpError(422,'Provider payment evidence does not match the order.');
            $captured=($payment['status']??'')==='captured'&&($payment['captured']??false)===true;
            if($captured){if($intent['payment_id']&&$intent['payment_id']!==$paymentId)throw new HttpError(409,'A different payment was already captured.');if(in_array($intent['state'],['refunded','part_refunded'],true))return $intent;
                $this->store->update('payments_paymentintent',$id,['state'=>'captured','payment_id'=>$paymentId,'updated_at'=>date('c')]);$this->store->update('orders_order',$order['id'],['payment_status'=>'paid','payment_reference'=>$paymentId]);if($order['payment_status']!=='paid')(new Orders($this->store))->event((int)$order['id'],$order['status'],$order['status'],'razorpay:'.$intent['mode'],$order['status']==='cancelled'?'Late payment received for cancelled order; review refund.':'Provider confirmed captured payment.');
            }elseif(($payment['status']??'')==='failed'&&!in_array($order['payment_status'],['paid','refunded'],true))$this->store->update('orders_order',$order['id'],['payment_status'=>'failed']);
            return $this->store->row('payments_paymentintent',$id);});
        if($intent['state']==='captured'&&$intent['mode']==='live'&&(new Billing($this->store))->timing()==='on_payment')(new Billing($this->store))->tryIssue((int)$intent['order_id']);return $intent;
    }
    public function reconcile(int $orderId): ?array {
        $intent=$this->forOrder($orderId);if(!$intent)return null;
        if(!$intent['provider_order_id'])return $this->start($orderId);
        $provider=new Razorpay($this->connection($intent));$rows=$provider->request('GET','orders/'.Razorpay::identifier($intent['provider_order_id'],'order').'/payments');
        foreach($rows['items']??[] as $row)if(($row['status']??'')==='captured'){$intent=$this->apply($intent['id'],$provider->payment($row['id']));break;}
        if($intent['payment_id'])$intent=$this->refundStatus($intent,$provider);return $intent;
    }
    private function refundStatus(array $intent,Razorpay $provider): array {
        $records=$provider->request('GET','payments/'.Razorpay::identifier($intent['payment_id'],'pay').'/refunds?count=100');$processed=0;
        foreach($records['items']??[] as $record){if(($record['payment_id']??'')!==$intent['payment_id'])continue;Razorpay::identifier((string)($record['id']??''),'rfnd');if(($record['status']??'')==='processed'&&is_int($record['amount']??null)&&$record['amount']>0)$processed+=$record['amount'];
            $local=$this->store->db->one("SELECT id FROM payments_refund WHERE tenant_id=? AND intent_id=? AND (provider_id=? OR replace(id::text,'-','')=?)",[$this->store->id(),$intent['id'],$record['id'],str_replace('-','',(string)($record['notes']['seer_refund']??''))]);if($local&&in_array($record['status']??'', ['processed','failed','pending'],true))$this->store->update('payments_refund',$local['id'],['provider_id'=>$record['id'],'state'=>$record['status']==='pending'?'submitted':$record['status'],'updated_at'=>date('c')]);
        }
        if($processed>(int)$intent['amount'])throw new HttpError(422,'Provider refund total exceeds the payment.');
        return $this->store->db->transaction(function()use($intent,$processed){$row=$this->store->row('payments_paymentintent',$intent['id'],true);if($processed<(int)$row['refunded_amount'])return $row;$values=['refunded_amount'=>$processed,'updated_at'=>date('c')];if($processed){$values['state']=$processed===(int)$row['amount']?'refunded':'part_refunded';if($processed===(int)$row['amount'])$this->store->update('orders_order',$row['order_id'],['payment_status'=>'refunded']);}
            if($processed===(int)$row['amount']&&!$row['credit_note_id']&&($bill=(new Billing($this->store))->forOrder((int)$row['order_id']))){try{$values['credit_note_id']=(new Billing($this->store))->credit((int)$bill['id'],$processed,'Razorpay refund')['id'];$values['bill_error']='';}catch(HttpError){$values['bill_error']='Refund verified; complete billing settings to issue the credit note.';}}$this->store->update('payments_paymentintent',$row['id'],$values);return $this->store->row('payments_paymentintent',$row['id']);});
    }
    public function refund(int $orderId,string $reason,string $actor): array {
        $reason=trim($reason);if(!$reason||mb_strlen($reason)>200)throw new HttpError(422,'Enter a refund reason up to 200 characters.');
        [$intent,$refund]=$this->store->db->transaction(function()use($orderId,$reason,$actor){$this->store->lock();$intent=$this->forOrder($orderId)??throw new HttpError(422,'No online payment exists.');$intent=$this->store->row('payments_paymentintent',$intent['id'],true);if($intent['state']!=='captured'||(int)$intent['refunded_amount'])throw new HttpError(422,'Only a fully captured, unrefunded payment can be refunded here.');
            $refund=$this->store->db->one("SELECT * FROM payments_refund WHERE tenant_id=? AND intent_id=? AND state<>'failed'",[$this->store->id(),$intent['id']]);if(!$refund)$refund=$this->store->insert('payments_refund',['id'=>Store::uuid(),'intent_id'=>$intent['id'],'amount'=>(int)$intent['amount'],'provider_id'=>'','state'=>'requested','reason'=>$reason,'actor'=>mb_substr($actor,0,150),'created_at'=>date('c'),'updated_at'=>date('c')]);return [$intent,$refund];});
        if($refund['provider_id'])return $refund;
        $provider=new Razorpay($this->connection($intent));try{$record=$provider->request('POST','payments/'.Razorpay::identifier($intent['payment_id'],'pay').'/refund',['amount'=>(int)$refund['amount'],'notes'=>['seer_refund'=>$refund['id']]],['X-Refund-Idempotency'=>$refund['id']]);}catch(ProviderError $error){if(!$error->uncertain)$this->store->update('payments_refund',$refund['id'],['state'=>'failed','updated_at'=>date('c')]);throw $error;}
        $providerId=Razorpay::identifier((string)($record['id']??''),'rfnd');$this->store->update('payments_refund',$refund['id'],['provider_id'=>$providerId,'state'=>'submitted','updated_at'=>date('c')]);$this->refundStatus($intent,$provider);return $this->store->row('payments_refund',$refund['id']);
    }
    public function webhook(string $mode,string $raw,string $signature,string $eventId): void {
        if(!in_array($mode,['test','live'],true)||strlen($raw)>1048576)throw new HttpError(400,'Invalid webhook.');$connection=$this->store->db->one('SELECT * FROM payments_razorpayconnection WHERE tenant_id=? AND mode=?',[$this->store->id(),$mode])??throw new HttpError(404,'Payment connection not found.');$secret=Crypto::decrypt($connection['_webhook_secret']);if(!$secret||!hash_equals(hash_hmac('sha256',$raw,$secret),$signature))throw new HttpError(403,'Invalid webhook signature.');
        try{$event=json_decode($raw,true,64,JSON_THROW_ON_ERROR);}catch(\JsonException){throw new HttpError(400,'Invalid JSON.');}$kind=$event['event']??'';$eventId=$eventId?:hash('sha256',$raw);if(strlen($eventId)>128)throw new HttpError(400,'Invalid event reference.');
        $this->store->db->transaction(function()use($mode,$event,$kind,$eventId){$this->store->lock();if($this->store->db->one('SELECT id FROM payments_paymentevent WHERE tenant_id=? AND mode=? AND event_id=?',[$this->store->id(),$mode,$eventId]))return;
            if(in_array($kind,['payment.captured','payment.failed','order.paid','refund.created','refund.processed','refund.failed'],true)){$entity=$event['payload']['payment']['entity']??null;$providerOrder=$entity['order_id']??($event['payload']['order']['entity']['id']??'');$paymentId=$entity['id']??($event['payload']['refund']['entity']['payment_id']??'');
                $row=$this->store->db->one('SELECT order_id FROM payments_paymentintent WHERE tenant_id=? AND mode=? AND ((provider_order_id<>\'\' AND provider_order_id=?) OR (payment_id<>\'\' AND payment_id=?))',[$this->store->id(),$mode,$providerOrder,$paymentId]);if(!$row)throw new HttpError(409,'Payment reference is not ready; retry this webhook.');$this->reconcile((int)$row['order_id']);}
            $this->store->insert('payments_paymentevent',['mode'=>$mode,'event_id'=>$eventId,'kind'=>mb_substr((string)$kind,0,60),'processed_at'=>date('c')]);});
    }
    public function saveConnection(string $mode,array $input): void {
        if(!in_array($mode,['test','live'],true))throw new HttpError(422,'Choose test or live mode.');$old=$this->store->db->one('SELECT * FROM payments_razorpayconnection WHERE tenant_id=? AND mode=?',[$this->store->id(),$mode]);
        $key=trim((string)($input['key_id']??''));$secret=(string)($input['key_secret']??'');$webhook=(string)($input['webhook_secret']??'');$enabled=!empty($input['enabled']);if(!preg_match('/^rzp_'.$mode.'_[a-zA-Z0-9]{1,60}$/D',$key))throw new HttpError(422,'Use a key ID from the selected Razorpay mode.');
        if($old&&($key!==$old['key_id']||$secret!=='')){$pending=$this->store->db->one("SELECT id FROM payments_paymentintent WHERE tenant_id=? AND connection_id=? LIMIT 1",[$this->store->id(),$old['id']]);if($pending)throw new HttpError(422,'These credentials are referenced by payment history. Keep them to support verification and refunds.');}
        $values=['mode'=>$mode,'enabled'=>$enabled,'key_id'=>$key,'_key_secret'=>$secret!==''?Crypto::encrypt($secret):($old['_key_secret']??''),'_webhook_secret'=>$webhook!==''?Crypto::encrypt($webhook):($old['_webhook_secret']??''),'updated_at'=>date('c')];
        if(!$values['_key_secret']||($webhook!==''&&strlen($webhook)<16))throw new HttpError(422,'Enter the key secret and a webhook secret of at least 16 characters.');if($enabled){if(!$values['_webhook_secret'])throw new HttpError(422,'Set the webhook secret before enabling checkout.');(new Razorpay($values))->request('GET','orders?count=1');}
        $this->store->db->transaction(function()use($old,$values,$enabled){$this->store->lock();$fresh=$this->store->db->one('SELECT * FROM payments_razorpayconnection WHERE tenant_id=? AND mode=?',[$this->store->id(),$values['mode']]);if(($fresh['updated_at']??null)!==($old['updated_at']??null))throw new HttpError(409,'Payment settings changed in another window. Reload before saving.');if($fresh&&($fresh['key_id']!==$values['key_id']||$fresh['_key_secret']!==$values['_key_secret'])&&$this->store->db->one('SELECT id FROM payments_paymentintent WHERE tenant_id=? AND connection_id=? LIMIT 1',[$this->store->id(),$fresh['id']]))throw new HttpError(422,'Preserve credentials referenced by payment history.');if($enabled)$this->store->db->rows('UPDATE payments_razorpayconnection SET enabled=FALSE WHERE tenant_id=?',[$this->store->id()]);if($old)$this->store->update('payments_razorpayconnection',$old['id'],$values);else $this->store->insert('payments_razorpayconnection',$values);});
    }
}
