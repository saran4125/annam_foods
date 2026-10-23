<?php
declare(strict_types=1);
namespace Annam;

final class Billing {
    public function __construct(private Store $store) {}
    public function get(int $id): array {return Store::json($this->store->row('billing_invoice',$id),['seller','buyer','lines']);}
    public function timing(): string {return $this->store->db->one('SELECT bill_timing FROM tenancy_billingprofile WHERE tenant_id=?',[$this->store->id()])['bill_timing']??'on_payment';}
    public function forOrder(int $id): ?array {$row=$this->store->db->one("SELECT id FROM billing_invoice WHERE tenant_id=? AND order_id=? AND kind<>'credit_note'",[$this->store->id(),$id]);return $row?$this->get((int)$row['id']):null;}
    public function tryIssue(int $id): ?array {
        try{return $this->issue($id);}catch(HttpError $error){
            $intent=$this->store->db->one('SELECT id FROM payments_paymentintent WHERE tenant_id=? AND order_id=?',[$this->store->id(),$id]);
            if($intent)$this->store->update('payments_paymentintent',$intent['id'],['bill_error'=>'Complete billing settings and review the paid total before issuing.']);return null;
        }
    }
    private function allocate(array $profile,string $series): array {
        $start=(int)date('Y')-((int)date('n')<4?1:0);$fy=sprintf('%02d-%02d',$start%100,($start+1)%100);
        $this->store->db->rows('INSERT INTO billing_invoicesequence(tenant_id,series,financial_year,next_no) VALUES(?,?,?,1) ON CONFLICT(tenant_id,series,financial_year) DO NOTHING',[$this->store->id(),$series,$fy]);
        $row=$this->store->db->one('SELECT * FROM billing_invoicesequence WHERE tenant_id=? AND series=? AND financial_year=? FOR UPDATE',[$this->store->id(),$series,$fy]);$seq=(int)$row['next_no'];
        $number=Settings::number($profile['number_format'],$profile['invoice_prefix'].($series==='credit'?'C':''),$fy,$seq);
        $this->store->update('billing_invoicesequence',$row['id'],['next_no'=>$seq+1]);return ['number'=>$number,'financial_year'=>$fy,'sequence_no'=>$seq];
    }
    public function issue(int $orderId): array {
        return $this->store->db->transaction(function()use($orderId){
            $this->store->lock();$order=(new Orders($this->store))->get($orderId,true);if($existing=$this->forOrder($orderId))return $existing;
            if($order['payment_status']!=='paid')throw new HttpError(422,'Payment must be received before issuing a bill.');
            $intent=$this->store->db->one('SELECT id,mode FROM payments_paymentintent WHERE tenant_id=? AND order_id=?',[$this->store->id(),$orderId]);if(($intent['mode']??'')==='test')throw new HttpError(422,'Test payments do not issue real bills.');
            $profile=$this->store->profile();Settings::validateProfile($profile);$seller=['name'=>$profile['legal_name'],'address'=>$profile['address'],'state'=>$profile['state'],'state_code'=>$profile['state_code'],'gstin'=>$profile['gstin'],'fssai_no'=>$profile['fssai_no'],'gst_mode'=>$profile['gst_mode'],'sac'=>$profile['sac'],'footer'=>$profile['footer'],'logo_url'=>image_url($this->store->config['theme']['billing_logo_url']??'')?:$this->store->logo(),'tagline'=>$this->store->config['tagline']];
            foreach(['gst_mode','prices_include_tax','round_total','delivery_fee_taxable','tax_rate'] as $key)if(array_key_exists($key,$order['pricing']))$profile[$key]=$order['pricing'][$key];
            Settings::validateProfile($profile);$seller['gst_mode']=$profile['gst_mode'];
            $customer=$this->store->row('orders_customer',$order['customer_id']);$slot=$order['slot_id']?$this->store->slot((int)$order['slot_id']):null;
            $buyer=['name'=>$order['address']['recipient_name']??$customer['name'],'phone'=>$order['address']['phone']??$customer['phone'],'delivery_address'=>$order['address'],'order_no'=>$order['order_no'],'channel'=>$order['channel'],'delivery_date'=>$order['delivery_date']??'','slot'=>$slot['label']??'','gstin'=>'','business_name'=>'','billing_address'=>''];
            if($order['buyer_gst'])$buyer=array_replace($buyer,$order['buyer_gst']);elseif(!$order['pricing'])foreach(['gstin','business_name','billing_address'] as $key)$buyer[$key]=$customer[$key];
            $regular=$profile['gst_mode']==='regular';$kind=$regular?'tax_invoice':($profile['gst_mode']==='composition'?'bill_of_supply':'bill');
            $interstate=!empty($order['address']['state_code'])&&$order['address']['state_code']!==$profile['state_code'];
            $source=$order['items'];$sum=array_sum(array_map(fn($line)=>Money::parse((string)$line['line_total']),$source));$discount=Money::parse($order['discount']);if($discount>$sum)throw new HttpError(422,'The order discount is invalid.');$remaining=$discount;$lines=[];$totals=['taxable'=>0,'cgst'=>0,'sgst'=>0,'igst'=>0];
            foreach($source as $index=>$line){
                $gross=Money::parse((string)$line['line_total']);$deduction=min($gross,$remaining,$index===count($source)-1?$remaining:($sum?Money::ratio($discount*$gross,$sum):0));$remaining-=$deduction;
                $item=empty($line['item_id'])?null:$this->store->db->one('SELECT tax_rate,sac FROM catalog_menuitem WHERE tenant_id=? AND id=?',[$this->store->id(),$line['item_id']]);
                $rate=$regular?Money::parse((string)($order['pricing']?($line['tax_rate']??$profile['tax_rate']):($item['tax_rate']??$profile['tax_rate']))):0;
                $lines[]=$this->line($line['name'],(int)$line['quantity'],(string)$line['unit_price'],$gross-$deduction,$rate,$deduction,$line['sac']??(($item['sac']??'')?:$profile['sac']),$profile,$interstate,$totals);
            }
            $fee=Money::parse($order['delivery_fee']);if($fee)$lines[]=$this->line('Delivery fee',1,$order['delivery_fee'],$fee,$regular&&$profile['delivery_fee_taxable']?Money::parse((string)$profile['tax_rate']):0,0,$profile['sac'],$profile,$interstate,$totals);
            $raw=array_sum($totals);$total=$profile['round_total']?Money::ratio($raw,100)*100:$raw;
            if($total!==Money::parse($order['total']))throw new HttpError(422,'Bill total does not match the paid order. Review tax and rounding settings.');
            $values=['kind'=>$kind,'series'=>'bill','order_id'=>$orderId,'original_id'=>null,'seller'=>json_encode($seller,JSON_THROW_ON_ERROR),'buyer'=>json_encode($buyer,JSON_THROW_ON_ERROR),'lines'=>json_encode($lines,JSON_THROW_ON_ERROR),'round_off'=>Money::signedDecimal($total-$raw),'total'=>Money::decimal($total),'amount_words'=>self::words($total),'payment_mode'=>$order['payment_mode'],'payment_ref'=>mb_substr($order['payment_reference']?:$order['external_ref'],0,120),'pdf'=>'','issued_at'=>date('c'),'sent_customer_at'=>null,'sent_owner_at'=>null]+$this->allocate($profile,'bill');
            foreach($totals as $key=>$amount)$values[$key]=Money::decimal($amount);$row=$this->store->insert('billing_invoice',$values);if($intent)$this->store->update('payments_paymentintent',$intent['id'],['bill_error'=>'']);return $this->get((int)$row['id']);
        });
    }
    private function line(string $name,int $qty,string $unit,int $gross,int $rate,int $discount,string $sac,array $profile,bool $interstate,array &$totals): array {
        $tax=Money::tax($gross,$rate,(bool)$profile['prices_include_tax']);$cgst=$interstate?0:Money::ratio($tax['tax'],2);$sgst=$interstate?0:$tax['tax']-$cgst;$igst=$interstate?$tax['tax']:0;
        $totals['taxable']+=$tax['base'];$totals['cgst']+=$cgst;$totals['sgst']+=$sgst;$totals['igst']+=$igst;
        return ['description'=>$name,'sac'=>$sac,'quantity'=>$qty,'unit_price'=>$unit,'discount'=>Money::decimal($discount),'taxable'=>Money::decimal($tax['base']),'tax_rate'=>Money::decimal($rate),'tax'=>Money::decimal($tax['tax']),'cgst'=>Money::decimal($cgst),'sgst'=>Money::decimal($sgst),'igst'=>Money::decimal($igst)];
    }
    public function credit(int $invoiceId,int $amount,string $reason): array {
        return $this->store->db->transaction(function()use($invoiceId,$amount,$reason){
            $this->store->lock();$original=$this->get($invoiceId);if($original['kind']==='credit_note')throw new HttpError(422,'Choose an original bill.');$full=Money::parse($original['total']);
            $used=$this->store->db->one('SELECT COALESCE(SUM(total),0) AS total FROM billing_invoice WHERE tenant_id=? AND original_id=?',[$this->store->id(),$invoiceId]);
            if($amount<=0||$amount+Money::parse($used['total'])>$full)throw new HttpError(422,'Credit exceeds the remaining bill value.');
            $values=array_intersect_key($original,array_flip(['seller','buyer','payment_mode','order_id']));$lines=$original['lines'];foreach($lines as &$line)foreach(['taxable','tax','cgst','sgst','igst'] as $key)$line[$key]=Money::decimal(Money::ratio(Money::parse((string)($line[$key]??'0'))*$amount,$full));unset($line);
            $raw=0;foreach(['taxable','cgst','sgst','igst'] as $key){$minor=Money::ratio(Money::parse($original[$key])*$amount,$full);$values[$key]=Money::decimal($minor);$raw+=$minor;}
            $values+=['kind'=>'credit_note','series'=>'credit','original_id'=>$invoiceId,'lines'=>$lines,'round_off'=>Money::signedDecimal($amount-$raw),'total'=>Money::decimal($amount),'amount_words'=>self::words($amount),'payment_ref'=>mb_substr($reason,0,120),'pdf'=>'','issued_at'=>date('c'),'sent_customer_at'=>null,'sent_owner_at'=>null]+$this->allocate($this->store->profile(),'credit');
            foreach(['seller','buyer','lines'] as $key)$values[$key]=json_encode($values[$key],JSON_THROW_ON_ERROR);$row=$this->store->insert('billing_invoice',$values);return $this->get((int)$row['id']);
        });
    }
    public static function words(int $minor): string {
        $ones=['zero','one','two','three','four','five','six','seven','eight','nine','ten','eleven','twelve','thirteen','fourteen','fifteen','sixteen','seventeen','eighteen','nineteen'];$tens=['','','twenty','thirty','forty','fifty','sixty','seventy','eighty','ninety'];
        $small=function(int $n)use($ones,$tens):string{$parts=[];if($n>=100){$parts[]=$ones[intdiv($n,100)].' hundred';$n%=100;}if($n>=20){$parts[]=$tens[intdiv($n,10)];$n%=10;}if($n)$parts[]=$ones[$n];return implode(' ',$parts);};
        $rupees=intdiv($minor,100);$parts=[];foreach([10000000=>'crore',100000=>'lakh',1000=>'thousand'] as $base=>$label){$n=intdiv($rupees,$base);if($n)$parts[]=$small($n).' '.$label;$rupees%=$base;}if($rupees)$parts[]=$small($rupees);$phrase=($parts?implode(' ',$parts):'zero').' rupees';if($minor%100)$phrase.=' and '.$small($minor%100).' paise';return ucwords($phrase).' Only';
    }
}
