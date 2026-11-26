<?php
declare(strict_types=1);
namespace Annam;

/** PHP adapter for main:apps/billing/presentation.py; issued values stay frozen. */
final class ReceiptPresentation {
    public static function details(array $invoice,array $payment):array {
        $seller=$invoice['seller'];$buyer=$invoice['buyer'];$address=$buyer['delivery_address']??[];$addressLines=[];$seen=[];
        foreach(['line1','line2','address','street','area','landmark'] as $key){$value=trim((string)($address[$key]??''));$fold=mb_strtolower($value);if($value!==''&&!isset($seen[$fold])){$addressLines[]=$value;$seen[$fold]=true;}}
        $locality=implode(', ',array_filter(array_map(fn($key)=>trim((string)($address[$key]??'')),['city','state','pincode']),fn($value)=>$value!==''));if($locality!=='')$addressLines[]=$locality;
        $lines=[];$discount=0;foreach($invoice['lines'] as $line){$entry=$line;$entry['amount']=Money::decimal(Money::parse($line['taxable'])+Money::parse($line['tax']));$entry['unit_price']=Money::decimal(Money::parse($line['unit_price']));$entry['discount_amount']=Money::parse((string)($line['discount']??'0'));$discount+=$entry['discount_amount'];$lines[]=$entry;}
        $logo=image_url($seller['logo_url']??'');if(($seller['logo_url']??'')==='/static/branding/annam-bill-logo.png')$logo='/media/brand/annam-bill-logo.png';
        return $payment+['logo_url'=>$logo,'tagline'=>$seller['tagline']??'','delivery_date'=>$buyer['delivery_date']??null,'address_lines'=>$addressLines,'collection'=>($address['fulfilment']??'')==='Collection','lines'=>$lines,'discount'=>$discount,'payment_label'=>['online'=>'Online payment','manual'=>'Manual payment','cod'=>'Cash on delivery'][$invoice['payment_mode']]??$invoice['payment_mode'],'cash_on_delivery'=>$invoice['payment_mode']==='cod','is_credit'=>$invoice['kind']==='credit_note','tax_registered'=>($seller['gst_mode']??'')==='regular','issued_unpaid'=>($buyer['payment_status_at_issue']??'paid')==='unpaid'];
    }
    public static function amount(string $value):string{return '₹'.Money::decimal(Money::parse($value));}
}
