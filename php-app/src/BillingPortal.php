<?php
declare(strict_types=1);
namespace Annam;

/** Thin billing HTTP adapter over the same scoped services used by management. */
final class BillingPortal {
    private const CHANNELS=['manual'=>'Manual billing','web'=>'Website billing','whatsapp'=>'WhatsApp billing'];
    public function __construct(private Store $store,private ?array $user){}
    public static function paymentLabel(string $value):string {return ['pending'=>'Awaiting payment','paid'=>'Paid','failed'=>'Failed','refunded'=>'Refunded','cod_pending'=>'Cash on delivery'][$value]??$value;}
    public static function channelLabel(string $value):string {return ['manual'=>'Entered by the kitchen','web'=>'Website','whatsapp'=>'WhatsApp'][$value]??$value;}
    private function view(string $view,array $data=[]):void {
        $billingPortal=true;$store=$this->store;$user=$this->user;$path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);$notice=$_SESSION['notice']??'';$notice_error=!empty($_SESSION['notice_error']);unset($_SESSION['notice'],$_SESSION['notice_error']);extract($data,EXTR_SKIP);
        ob_start();require ANNAM_ROOT.'/views/'.$view.'.php';$content=ob_get_clean();require ANNAM_ROOT.'/views/billing-layout.php';
    }
    public function handle(string $path,string $method):void {
        if($path==='/billing/login/'){
            if($this->user)redirect('/billing/');$error='';
            if($method==='POST'){
                if(Security::login($this->store->db,$this->store,(string)($_POST['username']??''),(string)($_POST['password']??''))){$next=(string)($_POST['next']??'/billing/');redirect(str_starts_with($next,'/billing/')&&Content::link($next)?$next:'/billing/');}
                $error='The username or password is incorrect, or this account has no store access.';
            }
            $next=(string)($_GET['next']??'/billing/');$this->view('billing-login',compact('error','next'));return;
        }
        if(!$this->user)redirect('/billing/login/?next='.rawurlencode($path));
        try{$this->route($path,$method);}catch(HttpError|ProviderError $e){
            if($method!=='POST')throw $e;
            $_SESSION['notice']=$e->getMessage();
            if($path==='/billing/new/'){$this->booking($e->getMessage(),$_POST);return;}
            if(preg_match('~^/billing/orders/(\d+)/~',$path,$m))redirect('/billing/orders/'.$m[1].'/');
            redirect('/billing/');
        }
    }
    private function route(string $path,string $method):void {
        $orders=new Orders($this->store);$billing=new Billing($this->store);$actor='owner:'.$this->user['username'];
        if($path==='/billing/logout/'){if($method!=='POST')throw new HttpError(405,'POST required.');$_SESSION=[];session_regenerate_id(true);redirect('/billing/login/');}
        if($path==='/billing/customer-lookup/'){
            if($method!=='GET')throw new HttpError(405,'GET required.');header('Content-Type: application/json');echo json_encode((new CustomerLookup($this->store))->find((string)($_GET['phone']??'')),JSON_THROW_ON_ERROR);return;
        }
        if($path==='/billing/new/'){
            if($method==='POST'){
                try{$input=$_POST;$input['payment_method']=$input['payment_mode']??'manual';$input['zone_id']=$input['zone']??'';$input['fulfilment_method']=($input['fulfilment_method']??'')==='courier'?'courier':'local';$input['booking_lines']=[];
                $n=filter_var($input['lines-TOTAL_FORMS']??'',FILTER_VALIDATE_INT);if($n===false||$n<1||$n>50)throw new HttpError(422,'Choose 1 to 50 item rows.');
                for($i=0;$i<$n;$i++)if(empty($input['lines-'.$i.'-DELETE']))$input['booking_lines'][]=['item'=>$input['lines-'.$i.'-item']??'','quantity'=>$input['lines-'.$i.'-quantity']??'','meal'=>$input['lines-'.$i.'-meal']??''];
                $o=$orders->staff($input,$actor);redirect('/billing/orders/'.$o['id'].'/');}catch(HttpError|\InvalidArgumentException $error){if($error instanceof HttpError&&$error->status!==422)throw $error;http_response_code(422);$this->booking($error->getMessage(),$_POST);return;}
            }
            $this->booking();return;
        }
        if($path==='/billing/settings/'){
            Settings::owner($this->user);
            $profile=$this->store->profile();$form_error='';
            if($method==='POST'){try{$input=$_POST;$input['bill_timing']='on_payment';(new Settings($this->store))->profile($input);$_SESSION['notice']='Billing settings saved for all three order sources.';redirect($path);}catch(HttpError|\InvalidArgumentException $error){if($error instanceof HttpError&&$error->status!==422)throw $error;http_response_code(422);$form_error=$error->getMessage();$profile=array_replace($profile,$_POST);foreach(['prices_include_tax','round_total','delivery_fee_taxable'] as $field)$profile[$field]=!empty($_POST[$field]);}}
            $this->view('billing-settings',compact('profile','form_error'));return;
        }
        if(preg_match('~^/billing/(?:bills|invoices)/(\d+)/(download/)?$~',$path,$m)){
            if($method!=='GET')throw new HttpError(405,'GET required.');$invoice=$billing->get((int)$m[1]);
            if(!empty($m[2])){header('Content-Type: application/pdf');header('Content-Disposition: attachment; filename="invoice.pdf"');echo InvoicePdf::invoice($invoice,$billing->paymentState($invoice));return;}
            $store=$this->store;require ANNAM_ROOT.'/views/bill.php';return;
        }
        if(preg_match('~^/billing/orders/(\d+)/(payment/|bill/|reconcile/|refund/)?$~',$path,$m)){
            $order=$orders->get((int)$m[1]);$action=$m[2]??'';
            if($action){
                if($method!=='POST')throw new HttpError(405,'POST required.');
                if(in_array($action,['reconcile/','refund/'],true)){
                    Settings::owner($this->user);$payments=new Payments($this->store);
                    if($action==='reconcile/')$payments->reconcile((int)$order['id']);
                    else{if(($_POST['confirmed_refund']??'')!=='yes')throw new HttpError(422,'Confirm the full refund before submitting.');$payments->refund((int)$order['id'],(string)($_POST['reason']??''),$actor);}
                    $_SESSION['notice']='Provider status checked. Financial status changes only after provider verification.';redirect('/billing/orders/'.$order['id'].'/');
                }
                try{if($action==='payment/'){
                    if(($_POST['action']??'')==='collect_on_delivery'){$orders->collectOnDelivery((int)$order['id'],$actor);$_SESSION['notice']='Payment not received: collect on delivery. Confirm actual collection here later.';redirect('/billing/orders/'.$order['id'].'/');}
                    $orders->confirm((int)$order['id'],$actor,(string)($_POST['reference']??''),($_POST['confirmed']??'')==='yes');
                }
                $invoice=$billing->issue((int)$order['id'],($_POST['issue_unpaid']??'')==='yes');redirect('/billing/bills/'.$invoice['id'].'/');}catch(HttpError|\InvalidArgumentException $error){if($error instanceof HttpError&&$error->status!==422)throw $error;$_SESSION['notice_error']=true;$_SESSION['notice']=$error->getMessage().' Any payment already confirmed remains recorded.';redirect('/billing/orders/'.$order['id'].'/');}
            }
            if($method!=='GET')throw new HttpError(405,'GET required.');$intent=(new Payments($this->store))->forOrder((int)$order['id']);$invoice=$billing->forOrder((int)$order['id']);$channel=$order['channel'];$this->view('billing-order',compact('order','intent','invoice','channel'));return;
        }
        if($method!=='GET')throw new HttpError(405,'GET required.');
        if($path==='/billing/'){
            $counts=[];foreach($this->store->db->rows('SELECT channel,COUNT(*) AS n FROM orders_order WHERE tenant_id=? GROUP BY channel',[$this->store->id()]) as $r)$counts[$r['channel']]=(int)$r['n'];$channels=self::CHANNELS;$this->view('billing-dashboard',compact('counts','channels'));return;
        }
        if(preg_match('~^/billing/(manual|web|whatsapp)/$~',$path,$m)){
            $channel=$m[1];$label=self::CHANNELS[$channel];$query=mb_substr(trim((string)($_GET['q']??'')),0,80);$status=(string)($_GET['status']??'');$where=' WHERE o.tenant_id=? AND o.channel=?';$args=[$this->store->id(),$channel];
            if($query!==''){$where.=' AND (o.order_no ILIKE ? OR c.name ILIKE ? OR c.phone ILIKE ? OR (o.address->>\'recipient_name\') ILIKE ?)';array_push($args,'%'.$query.'%','%'.$query.'%','%'.$query.'%','%'.$query.'%');}
            if($status==='paid')$where.=" AND o.payment_status='paid'";elseif($status==='unpaid')$where.=" AND o.payment_status<>'paid'";
            $from=' FROM orders_order o JOIN orders_customer c ON c.id=o.customer_id AND c.tenant_id=o.tenant_id'.$where;$total=(int)$this->store->db->one('SELECT COUNT(*) AS n'.$from,$args)['n'];$pages=max(1,(int)ceil($total/25));$page=max(1,min($pages,(int)($_GET['page']??1)));
            $records=$this->store->db->rows('SELECT o.*,c.name AS customer_name,c.phone AS customer_phone'.$from.' ORDER BY o.placed_at DESC,o.id DESC LIMIT 25 OFFSET '.(($page-1)*25),$args);foreach($records as &$r){$r=Store::json($r,['address']);$r['invoice']=$billing->forOrder((int)$r['id']);}unset($r);
            $this->view('billing-orders',compact('channel','label','query','status','records','page','pages','total'));return;
        }
        throw new HttpError(404,'Billing page not found.');
    }
    private function booking(string $error='',array $values=[]):void {
        if($_SERVER['REQUEST_METHOD']==='GET')foreach(['phone'=>20,'name'=>120] as $field=>$limit)if(isset($_GET[$field])&&is_string($_GET[$field]))$values[$field]=mb_substr(trim($_GET[$field]),0,$limit);
        $token=is_string($values['token']??null)?$values['token']:'';if(!preg_match('/^[a-f0-9]{32}$/D',$token)||!isset($_SESSION['staff_tokens'][$token])){$token=bin2hex(random_bytes(16));$_SESSION['staff_tokens'][$token]=time();}$_SESSION['staff_tokens']=array_slice($_SESSION['staff_tokens'],-30,null,true);
        $catalog=[];foreach($this->store->items() as $item){if(!$item['active']||!($item['in_stock']??true)||(!empty($item['quantity_tracked'])&&$item['stock_quantity']<=0))continue;$groups=$item['fulfilment']==='courier'?['snacks']:(new Catalog($this->store))->meals($item);$groups=array_values(array_intersect($groups,['breakfast','lunch','dinner','snacks']));$category=$item['category_id']?$this->store->db->one('SELECT name FROM catalog_menucategory WHERE tenant_id=? AND id=?',[$this->store->id(),$item['category_id']]):null;$catalog[]=['id'=>(int)$item['id'],'name'=>$item['name'],'price'=>(string)$item['price'],'category'=>$category['name']??'','groups'=>$groups?:['other']];}
        $zones=$this->store->db->rows('SELECT * FROM delivery_deliveryzone WHERE tenant_id=? AND active ORDER BY area_name',[$this->store->id()]);$areas=array_map(fn($z)=>['id'=>(int)$z['id'],'fee'=>(string)$z['delivery_fee'],'minimum'=>(string)$z['min_order']],$zones);$channel=($values['channel']??$_GET['channel']??'manual')==='whatsapp'?'whatsapp':'manual';$this->view('billing-booking',compact('token','catalog','zones','areas','channel','error','values'));
    }
}
