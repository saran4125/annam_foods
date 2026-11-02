<?php
declare(strict_types=1);
namespace Annam;

final class Courier {
    public function __construct(private Store $store){}
    public function get(int $orderId,bool $lock=false):?array {return $this->store->db->one('SELECT * FROM orders_couriercharge WHERE tenant_id=? AND order_id=?'.($lock?' FOR UPDATE':''),[$this->store->id(),$orderId]);}
    public function notice(array $order,string $body,string $key):void {
        $cfg=$this->store->config['checkout_settings'];$enabled=$cfg['courier_notifications_enabled']??false;
        foreach(['customer'=>$order['address']['phone']??'','team'=>($cfg['courier_team_phone']??'')?:$this->store->config['support_phone']] as $role=>$phone){
            if(!$phone)continue;$payload=['kind'=>'text','body'=>'Order '.$order['order_no']."\n".$body];
            if($enabled){$name=$cfg['courier_'.$role.'_template']??'';if(!$name)throw new HttpError(422,'Configure both approved courier WhatsApp templates before enabling notifications.');$payload=['kind'=>'template','name'=>$name,'language'=>$cfg['courier_template_language']??'en','params'=>[$order['order_no'],$body]];}
            $message=(new Messaging($this->store))->queue(preg_replace('/\D/','',$phone),$payload,'courier_'.$role,'courier:'.$order['id'].':'.$key.':'.$role);
            if(!$enabled&&$message['status']==='pending'){$this->store->update('messaging_outboundmessage',$message['id'],['status'=>'held']);$this->store->db->rows("UPDATE messaging_whatsappmessage SET status='held' WHERE tenant_id=? AND outbound_id=?",[$this->store->id(),$message['id']]);}
        }
    }
    public function prepare(array $order):array {
        $cfg=$this->store->config['checkout_settings'];if(!(($cfg['courier_team_phone']??'')?:$this->store->config['support_phone']))throw new HttpError(422,'Configure the team WhatsApp phone before accepting courier orders.');
        $charge=$this->get((int)$order['id'])??$this->store->insert('orders_couriercharge',['order_id'=>$order['id'],'amount'=>null,'dispatched_at'=>null,'courier_name'=>'','tracking_number'=>'','paid_at'=>null,'payment_reference'=>'','created_at'=>date('c')]);$this->notice($order,Delivery::COURIER,'disclosure');return $charge;
    }
    public function dispatch(int $orderId,string $amount,string $courier,string $tracking,string $actor):array {
        return $this->store->db->transaction(function()use($orderId,$amount,$courier,$tracking,$actor){$order=(new Orders($this->store))->get($orderId,true);$charge=$this->get($orderId,true)??throw new HttpError(422,'This order has no deferred courier charge.');
            if(!in_array($order['status'],['out_for_delivery','delivered'],true)||!trim($courier)||!trim($tracking))throw new HttpError(422,'Mark the order dispatched and enter the courier service and tracking number.');
            $value=Money::decimal(Money::parse($amount));if(Money::parse($value)>9999999999)throw new HttpError(422,'Courier amount is too large.');
            if($charge['dispatched_at']){if($charge['amount']===$value&&$charge['tracking_number']===$tracking)return $charge;throw new HttpError(409,'A confirmed courier charge cannot be overwritten.');}
            $this->store->update('orders_couriercharge',$charge['id'],['amount'=>$value,'dispatched_at'=>date('c'),'courier_name'=>mb_substr(trim($courier),0,120),'tracking_number'=>mb_substr(trim($tracking),0,120)]);
            $this->notice($order,'Your Snacks order has been dispatched via '.$courier.'. Tracking: '.$tracking.'. Courier charge payable separately: ₹'.$value.'. This is in addition to your food order payment.','dispatch');(new Orders($this->store))->event($orderId,$order['status'],$order['status'],$actor,'Courier charge confirmed: ₹'.$value);return $this->get($orderId);
        });
    }
    public function confirm(int $orderId,string $reference,string $actor):array {
        return $this->store->db->transaction(function()use($orderId,$reference,$actor){$order=(new Orders($this->store))->get($orderId,true);$charge=$this->get($orderId,true)??throw new HttpError(422,'Courier charge not found.');
            if(!$charge['dispatched_at']||$charge['amount']===null)throw new HttpError(422,'Confirm the dispatched courier amount first.');
            if($actor!=='razorpay'&&$this->store->db->one("SELECT id FROM payments_courierpayment WHERE tenant_id=? AND charge_id=? AND mode='live' AND state IN ('creating','ready','uncertain')",[$this->store->id(),$charge['id']]))throw new HttpError(422,'Verify the pending online courier payment first.');
            if(!$charge['paid_at']){$this->store->update('orders_couriercharge',$charge['id'],['paid_at'=>date('c'),'payment_reference'=>mb_substr($reference,0,120)]);$this->notice($order,'Courier payment received: ₹'.$charge['amount'].'. Reference: '.$reference,'paid');(new Orders($this->store))->event($orderId,$order['status'],$order['status'],$actor,'Courier payment received: ₹'.$charge['amount']);}return $this->get($orderId);
        });
    }
    public function release():int {
        $cfg=$this->store->config['checkout_settings'];if(empty($cfg['courier_notifications_enabled'])||empty($cfg['courier_customer_template'])||empty($cfg['courier_team_template']))throw new HttpError(422,'Enable and configure verified courier WhatsApp templates before releasing drafts.');
        return $this->store->db->transaction(function()use($cfg){$rows=$this->store->db->rows("SELECT * FROM messaging_outboundmessage WHERE tenant_id=? AND status='held' AND purpose IN ('courier_customer','courier_team') FOR UPDATE",[$this->store->id()]);foreach($rows as $row){$role=substr($row['purpose'],8);$parts=explode(':',$row['dedupe_key']);$order=(new Orders($this->store))->get((int)$parts[1]);$old=json_decode($row['payload'],true);$body=explode("\n",$old['body']??'',2)[1]??'';$payload=['kind'=>'template','name'=>$cfg['courier_'.$role.'_template'],'language'=>$cfg['courier_template_language']??'en','params'=>[$order['order_no'],$body]];MessagePayload::graph($row['to_phone'],$payload);$this->store->update('messaging_outboundmessage',$row['id'],['status'=>'pending','payload'=>json_encode($payload,JSON_THROW_ON_ERROR)]);$this->store->db->rows("UPDATE messaging_whatsappmessage SET status='queued' WHERE tenant_id=? AND outbound_id=?",[$this->store->id(),$row['id']]);}return count($rows);});
    }
}
