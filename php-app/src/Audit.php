<?php
declare(strict_types=1);
namespace Annam;
/** Read-only migration fingerprints. No names, addresses, messages or secrets in reports. */
final class Audit {
    public const TABLES=['catalog_slot','catalog_menucategory','catalog_menuitem','catalog_menuschedule','catalog_menuday','delivery_deliveryzone','content_page','content_banner','content_storefrontimage','tenancy_tenantconfig','tenancy_billingprofile','tenancy_tenantsecrets','orders_customer','orders_address','orders_order','orders_orderevent','billing_invoice','billing_invoicesequence','billing_invoicerequest','payments_razorpayconnection','payments_paymentintent','payments_refund','payments_paymentevent','messaging_outboundmessage','messaging_whatsappconversation','messaging_whatsappmessage','messaging_whatsappreceipt','messaging_whatsappforwardevent'];
    public function __construct(private Store $store) {}
    public function fingerprints(): array {
        return $this->store->db->transaction(function(){
            $this->store->db->rows('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');$tables=[];
            foreach(self::TABLES as $table){$hash=hash_init('sha256');$count=0;$offset=0;do{$rows=$this->store->db->rows("SELECT * FROM $table WHERE tenant_id=? ORDER BY id LIMIT 500 OFFSET ?",[$this->store->id(),$offset]);foreach($rows as $row){ksort($row);foreach($row as &$value)if(is_resource($value))$value=['binary_sha256'=>hash('sha256',stream_get_contents($value))];unset($value);hash_update($hash,json_encode($row,JSON_THROW_ON_ERROR|JSON_INVALID_UTF8_SUBSTITUTE)."\n");$count++;}$offset+=500;}while(count($rows)===500);$tables[$table]=['count'=>$count,'sha256'=>hash_final($hash)];}
            return ['version'=>1,'store'=>$this->store->tenant['slug'],'created_at'=>gmdate('c'),'tables'=>$tables];
        });
    }
    public function readiness(): array {
        $checks=[];try{Settings::validateProfile($this->store->profile());$checks['billing_profile']=true;}catch(\Throwable){$checks['billing_profile']=false;}
        try{Settings::validateCheckout($this->store->config['checkout_settings']);$checks['delivery_settings']=true;}catch(\Throwable){$checks['delivery_settings']=false;}
        $refs=(new Backup($this->store))->references();$checks['all_referenced_media_present']=!$refs['missing']&&!$refs['external'];
        $checks['credentials_decrypt']=true;foreach($this->store->db->rows('SELECT _key_secret,_webhook_secret FROM payments_razorpayconnection WHERE tenant_id=?',[$this->store->id()]) as $row)foreach($row as $cipher)if($cipher)try{Crypto::decrypt($cipher);}catch(\Throwable){$checks['credentials_decrypt']=false;}
        $secrets=(new Messaging($this->store))->secrets();foreach(['wa_token_enc','wa_app_secret_enc','n8n_auth_token_enc','wa_sync_token_enc','razorpay_secret_enc','rzp_webhook_secret_enc'] as $key)if($secrets[$key])try{Crypto::decrypt($secrets[$key]);}catch(\Throwable){$checks['credentials_decrypt']=false;}
        $bad=$this->store->db->one("SELECT count(*) AS n FROM billing_invoice b JOIN orders_order o ON o.id=b.order_id AND o.tenant_id=b.tenant_id WHERE b.tenant_id=? AND b.kind<>'credit_note' AND b.total<>o.total",[$this->store->id()]);$checks['issued_bill_totals_match_orders']=(int)$bad['n']===0;
        $checks['login_throttle_installed']=$this->store->db->one("SELECT to_regclass('public.php_login_attempt') AS name")['name']!==null;
        return ['checks'=>$checks,'database_checks_passed'=>!in_array(false,$checks,true),'missing_media'=>$refs['missing'],'external_image_count'=>count($refs['external']),'external_acceptance_required'=>['Hostinger PDO PostgreSQL and outbound TLS to Supabase','Restore rehearsal of database and complete media backup','Razorpay sandbox capture, failed payment, signed webhook, retry and refund','Meta/n8n incoming, outgoing, receipt and attachment verification','Hosting cron execution and permissions','Mobile/customer acceptance and HTTPS/domain cutover']];
    }
}
