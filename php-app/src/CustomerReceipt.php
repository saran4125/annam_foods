<?php
declare(strict_types=1);
namespace Annam;

final class CustomerReceipt {
    public function __construct(private Store $store) {}
    public function state(array $order,string $reference): array {
        $intent=(new Payments($this->store))->forOrder((int)$order['id']);$invoice=(new Billing($this->store))->forOrder((int)$order['id']);$base='/checkout/complete/'.$reference.'/';$test=($intent['mode']??'')==='test';$paid=$order['payment_status']==='paid';
        $download=$test?($paid&&$intent['state']==='captured'?$base.'test-receipt/download/':''):($invoice?$base.'bill/download/':'');
        return ['status'=>$order['payment_status'],'order_status'=>$order['status'],'payment_label'=>ucfirst(str_replace('_',' ',$order['payment_status'])),'order_label'=>ucfirst(str_replace('_',' ',$order['status'])),'paid'=>$paid,'test'=>$test,'invoice_url'=>$invoice&&!$test?$base.'bill/':'','download_url'=>$download];
    }
    public function pdf(array $order,bool $test): string {
        $intent=(new Payments($this->store))->forOrder((int)$order['id']);
        if($test){if(($intent['mode']??'')!=='test'||$intent['state']!=='captured'||$order['payment_status']!=='paid')throw new HttpError(404,'Verified test receipt unavailable.');return InvoicePdf::test($order);}
        if(($intent['mode']??'')==='test')throw new HttpError(404,'Invoice unavailable.');
        $invoice=(new Billing($this->store))->forOrder((int)$order['id'])??throw new HttpError(404,'Invoice is not issued yet.');return InvoicePdf::invoice($invoice,(new Billing($this->store))->paymentState($invoice));
    }
}
