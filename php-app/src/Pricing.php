<?php
declare(strict_types=1);
namespace Annam;

final class Pricing {
    public static function totals(array $lines,int $fee,array $profile): array {
        $regular=$profile['gst_mode']==='regular';$subtotal=$tax=$extra=0;
        foreach($lines as &$line) {
            $rate=$regular?Money::parse((string)($line['tax_rate']??$profile['tax_rate'])):0;
            $line['tax_rate']=Money::decimal($rate);$line['sac']=$line['sac']??$profile['sac'];
            $gross=Money::parse((string)$line['line_total']);$subtotal+=$gross;
            $amount=Money::tax($gross,$rate,(bool)$profile['prices_include_tax']);$tax+=$amount['tax'];
            if(!$profile['prices_include_tax']) $extra+=$amount['tax'];
        }unset($line);
        $feeTax=Money::tax($fee,$regular&&$profile['delivery_fee_taxable']?Money::parse((string)$profile['tax_rate']):0,(bool)$profile['prices_include_tax']);
        $tax+=$feeTax['tax'];if(!$profile['prices_include_tax']) $extra+=$feeTax['tax'];
        $raw=$subtotal+$fee+$extra;$total=$profile['round_total']?Money::ratio($raw,100)*100:$raw;
        if($total<=0||$total>=10000000000) throw new HttpError(422,'Order total must be positive and below ₹10 crore.');
        $settings=array_intersect_key($profile,array_flip(['gst_mode','prices_include_tax','round_total','delivery_fee_taxable','tax_rate']));
        return ['lines'=>$lines,'subtotal'=>$subtotal,'delivery_fee'=>$fee,'tax'=>$tax,'extra_tax'=>$extra,'round_off'=>$total-$raw,'total'=>$total,'pricing'=>$settings];
    }
    public static function line(array $item,int $quantity,?string $price=null): array {
        if($quantity<1||$quantity>999) throw new HttpError(422,'Quantity must be between 1 and 999.');
        $unit=Money::parse($price??$item['price']);
        return ['item_id'=>(int)$item['id'],'name'=>$item['name'],'quantity'=>$quantity,'unit_price'=>Money::decimal($unit),'line_total'=>Money::decimal($unit*$quantity),'is_veg'=>(bool)$item['is_veg'],'tax_rate'=>$item['tax_rate'],'sac'=>$item['sac']?:null];
    }
}
