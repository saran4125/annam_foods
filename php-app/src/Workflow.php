<?php
declare(strict_types=1);
namespace Annam;

/** HTTP adapter; business rules stay in domain services. */
final class Workflow {
    public function __construct(private Store $store,private ?array $user,private \Closure $render) {}
    private function view(string $name,array $data=[],bool $admin=false): void {($this->render)($name,$data,$admin);}
    private function actor(): string {return (string)($this->user['username']??'customer:web');}
    public function callbacks(string $path,string $method): bool {
        if(preg_match('~^/platform/webhooks/'.preg_quote($this->store->tenant['slug'],'~').'/razorpay/(test|live)/$~',$path,$match)){
            if($method!=='POST')throw new HttpError(405,'POST required.');(new Payments($this->store))->webhook($match[1],self::raw(),$_SERVER['HTTP_X_RAZORPAY_SIGNATURE']??'',$_SERVER['HTTP_X_RAZORPAY_EVENT_ID']??'');self::json(['ok'=>true]);return true;
        }
        $prefix='/platform/webhooks/'.$this->store->tenant['slug'];
        if(in_array($path,['/webhooks/whatsapp/',$prefix.'/whatsapp/','/webhooks/whatsapp/n8n/',$prefix.'/whatsapp/n8n/'],true)){
            $messaging=new Messaging($this->store);if($method==='GET'&&!str_contains($path,'n8n')){$saved=$messaging->secrets()['wa_verify_token'];$provided=$_GET['hub_verify_token']??$_GET['hub.verify_token']??'';if(!$saved||!is_string($provided)||!hash_equals($saved,$provided)||($_GET['hub_mode']??$_GET['hub.mode']??'')!=='subscribe')throw new HttpError(403,'Verification failed.');header('Content-Type: text/plain');echo substr((string)($_GET['hub_challenge']??$_GET['hub.challenge']??''),0,200);return true;}
            if($method!=='POST')throw new HttpError(405,'POST required.');if(str_contains($path,'n8n'))$messaging->sync(self::raw(),$_SERVER['HTTP_AUTHORIZATION']??'');else $messaging->webhook(self::raw(),$_SERVER['HTTP_X_HUB_SIGNATURE_256']??'');self::json(['ok'=>true]);return true;
        }return false;
    }
    private static function raw(): string {$stream=fopen('php://input','rb');$raw=stream_get_contents($stream,1048577);fclose($stream);if(strlen($raw)>1048576)throw new HttpError(413,'Webhook too large.');return $raw;}
    private static function json(array $data): void {header('Content-Type: application/json');echo json_encode($data,JSON_THROW_ON_ERROR);}
    public function publicRoute(string $path,string $method): bool {
        $checkout=new Checkout($this->store);
        if($path==='/checkout/'){
            if($method==='POST'){$review=$checkout->review($_POST);$this->view('checkout-review',$review);return true;}
            $quote=Cart::quote($this->store);if(!$quote['lines'])redirect('/cart/');$choices=$checkout->choices();$areas=$this->store->db->rows('SELECT id,area_name,pincode FROM delivery_deliveryzone WHERE tenant_id=? AND active ORDER BY area_name',[$this->store->id()]);$this->view('checkout',compact('quote','choices','areas'));return true;
        }
        if($path==='/checkout/place/'&&$method==='POST'){$reference=(string)($_POST['reference']??'');$checkout->place($reference);redirect('/checkout/complete/'.$reference.'/');}
        if(preg_match('~^/checkout/complete/([a-f0-9-]{32,36})/(pay/|payment/|verify/|status/|bill/)?$~',$path,$match)){
            $reference=$match[1];$order=$checkout->guest($reference);$suffix=$match[2]??'';$payments=new Payments($this->store);
            if($suffix==='bill/'){$invoice=(new Billing($this->store))->forOrder((int)$order['id'])??throw new HttpError(404,'The bill is not available yet.');$this->bill($invoice);return true;}
            if($suffix==='pay/') {if($method!=='POST')throw new HttpError(405,'Use the payment button.');$payments->start((int)$order['id']);redirect('/checkout/complete/'.$reference.'/');}
            if($suffix==='verify/') {if($method!=='POST')throw new HttpError(405,'POST required.');$payments->verify((int)$order['id'],$_POST);redirect('/checkout/complete/'.$reference.'/');}
            if($suffix==='status/'&&$method==='POST'){$payments->reconcile((int)$order['id']);redirect('/checkout/complete/'.$reference.'/');}
            $intent=$payments->forOrder((int)$order['id']);if($suffix==='payment/'){if(!$intent||!$intent['provider_order_id'])throw new HttpError(422,'Start the payment first.');self::json(['key'=>$intent['key_id'],'order_id'=>$intent['provider_order_id'],'amount'=>(int)$intent['amount'],'currency'=>'INR','name'=>$this->store->name()]);return true;}
            $invoice=(new Billing($this->store))->forOrder((int)$order['id']);$this->view('order-receipt',compact('order','intent','invoice','reference'));return true;
        }return false;
    }
    public function admin(string $path,string $method): bool {
        $orders=new Orders($this->store);$payments=new Payments($this->store);$billing=new Billing($this->store);
        if($path==='/manage/orders/'){$records=$orders->all($_GET['channel']??null,trim((string)($_GET['q']??'')));$this->view('orders',compact('records'),true);return true;}
        if($path==='/manage/orders/new/'){
            if($method==='POST'){$order=$orders->staff($_POST,$this->actor());redirect('/manage/orders/'.$order['id'].'/');}
            $token=bin2hex(random_bytes(16));$_SESSION['staff_tokens'][$token]=time();$_SESSION['staff_tokens']=array_slice($_SESSION['staff_tokens'],-30,null,true);$items=$this->store->items();$zones=$this->store->db->rows('SELECT * FROM delivery_deliveryzone WHERE tenant_id=? AND active ORDER BY area_name',[$this->store->id()]);$conversation=null;if(!empty($_GET['conversation']))$conversation=$this->store->row('messaging_whatsappconversation',(int)$_GET['conversation']);$this->view('booking',compact('token','items','zones','conversation'),true);return true;
        }
        if(preg_match('~^/manage/orders/(\d+)/(status/|confirm/|payment/|bill/|reconcile/|refund/)?$~',$path,$match)){
            $id=(int)$match[1];$order=$orders->get($id);$action=$match[2]??'';if($action==='payment/')$action='confirm/';
            if($action){if($method!=='POST')throw new HttpError(405,'Use the action form.');
                if($action==='status/')$orders->advance($id,(string)($_POST['status']??''),$this->actor(),(string)($_POST['note']??''),['name'=>$_POST['rider_name']??'','phone'=>$_POST['rider_phone']??'']);
                else{Settings::owner($this->user);match($action){'confirm/'=>$orders->confirm($id,$this->actor(),(string)($_POST['reference']??''),!empty($_POST['received'])),'bill/'=>$billing->issue($id),'reconcile/'=>$payments->reconcile($id),'refund/'=>$payments->refund($id,(string)($_POST['reason']??''),$this->actor()),default=>null};}
                redirect('/manage/orders/'.$id.'/');
            }
            $intent=$payments->forOrder($id);$invoice=$billing->forOrder($id);$events=$this->store->db->rows('SELECT * FROM orders_orderevent WHERE tenant_id=? AND order_id=? ORDER BY at,id',[$this->store->id(),$id]);$customer=$this->store->row('orders_customer',$order['customer_id']);$this->view('order-detail',compact('order','intent','invoice','events','customer'),true);return true;
        }
        if(preg_match('~^/(?:manage/bills|billing/invoices)/(\d+)/$~',$path,$match)){$this->bill($billing->get((int)$match[1]));return true;}
        if($path==='/manage/settings/media-backup/'){Settings::owner($this->user);if($method!=='POST')throw new HttpError(405,'Use the download button.');(new Backup($this->store))->download();return true;}
        if(in_array($path,['/manage/billing-settings/','/manage/billing/'],true)){
            Settings::owner($this->user);if($method==='POST'){(new Settings($this->store))->profile($_POST);$_SESSION['notice']='Billing settings saved. Issued bills remain unchanged.';redirect($path);}$profile=$this->store->profile();$this->view('billing-settings',compact('profile'),true);return true;
        }
        if($path==='/manage/checkout-settings/'){
            Settings::owner($this->user);if($method==='POST'){(new Settings($this->store))->checkout($_POST);$_SESSION['notice']='Checkout settings saved.';redirect($path);}$settings=$this->store->config['checkout_settings'];$this->view('checkout-settings',compact('settings'),true);return true;
        }
        if($path==='/manage/payments/razorpay/'){
            Settings::owner($this->user);$mode=(string)($_GET['mode']??'test');if(!in_array($mode,['test','live'],true))throw new HttpError(422,'Choose test or live mode.');if($method==='POST'){$payments->saveConnection($mode,$_POST);$_SESSION['notice']='Payment settings saved.';redirect($path.'?mode='.$mode);}$connection=$this->store->db->one('SELECT mode,enabled,key_id FROM payments_razorpayconnection WHERE tenant_id=? AND mode=?',[$this->store->id(),$mode])??['mode'=>$mode,'enabled'=>false,'key_id'=>''];$this->view('razorpay-settings',compact('connection','mode'),true);return true;
        }
        if(preg_match('~^/manage/whatsapp/messages/(\d+)/media/$~',$path,$attachment)){Attachment::serve($this->store,(int)$attachment[1]);return true;}
        if($path==='/manage/whatsapp/settings/'){
            Settings::owner($this->user);$messaging=new Messaging($this->store);if($method==='POST'){$messaging->saveSettings($_POST);$_SESSION['notice']='WhatsApp settings saved.';redirect($path);}$secrets=$messaging->secrets();$integration=array_intersect_key($secrets,array_flip(['wa_provider','wa_phone_number_id','wa_waba_id','n8n_send_url','n8n_receive_url']));unset($secrets);$this->view('whatsapp-settings',compact('integration'),true);return true;
        }
        if($path==='/manage/whatsapp/'||preg_match('~^/manage/whatsapp/(\d+)/(reply/|read/)?$~',$path,$match)){
            $selected=isset($match[1])?(int)$match[1]:null;$conversation=$selected?$this->store->row('messaging_whatsappconversation',$selected):null;
            if($method==='POST'&&$conversation){if(($match[2]??'')==='reply/')(new Messaging($this->store))->reply($selected,(string)($_POST['body']??''),(string)($_POST['token']??''),$this->actor());elseif(($match[2]??'')==='read/')$this->store->update('messaging_whatsappconversation',$selected,['unread_count'=>0]);else throw new HttpError(405,'Use a conversation action.');redirect('/manage/whatsapp/'.$selected.'/');}
            $conversations=$this->store->db->rows('SELECT * FROM messaging_whatsappconversation WHERE tenant_id=? ORDER BY last_message_at DESC LIMIT 200',[$this->store->id()]);$messages=$selected?$this->store->db->rows('SELECT * FROM messaging_whatsappmessage WHERE tenant_id=? AND conversation_id=? ORDER BY occurred_at DESC,id DESC LIMIT 200',[$this->store->id(),$selected]):[];$messages=array_reverse($messages);$token=bin2hex(random_bytes(16));$_SESSION['reply_tokens'][$token]=time();$_SESSION['reply_tokens']=array_slice($_SESSION['reply_tokens'],-30,null,true);$this->view('inbox',compact('conversations','conversation','messages','token'),true);return true;
        }
        return false;
    }
    private function bill(array $invoice): void {$store=$this->store;require ANNAM_ROOT.'/views/bill.php';}
}
