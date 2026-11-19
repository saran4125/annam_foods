<?php
declare(strict_types=1);
namespace Annam;

/** All amounts and legal details come from the issued immutable snapshot. */
final class InvoicePdf {
    private static function document(string $title,string $html,bool $heading=true): string {
        require_once ANNAM_ROOT.'/resources/vendor/tcpdf/tcpdf.php';
        $pdf=new \TCPDF();$pdf->setPrintHeader(false);$pdf->setPrintFooter(false);$pdf->SetCreator('Annam Foods');$pdf->SetTitle($title);$pdf->SetMargins(16,16,16);$pdf->SetAutoPageBreak(true,16);$pdf->SetFont('dejavusans','',10);$pdf->AddPage();$pdf->writeHTML(($heading?'<h1>'.e($title).'</h1>':'').$html);return $pdf->Output('receipt.pdf','S');
    }
    public static function invoice(array $invoice, ?array $payment=null): string {
        $payment??=['payment_received'=>($invoice['buyer']['payment_status_at_issue']??'paid')!=='unpaid','payment_refunded'=>false,'amount_due'=>$invoice['total'],'settlement_reference'=>$invoice['payment_ref']];
        $seller=$invoice['seller'];$buyer=$invoice['buyer'];$credit=$invoice['kind']==='credit_note';$regular=($seller['gst_mode']??'')==='regular';
        $status=$credit?'CREDIT NOTE ISSUED':(!empty($payment['payment_refunded'])?'PAYMENT REFUNDED':($payment['payment_received']?'PAYMENT RECEIVED':'UNPAID — PAYMENT NOT RECEIVED'));
        $logo=Media::file((string)($seller['logo_url']??''));$html=($logo?'<p style="text-align:center"><img src="'.e($logo).'" width="90"></p>':'').'<h2 style="text-align:center">'.e($seller['name']).'</h2><p style="text-align:center">'.e($seller['tagline']??'').'<br><b>'.e($status).'</b></p>';
        $html.='<table cellpadding="5"><tr><td><b>Document number</b><br>'.e($invoice['number']).'</td><td align="right"><b>Issued</b><br>'.e(date('j M Y, g:i A',strtotime($invoice['issued_at']))).'</td></tr><tr><td><b>Order</b><br>'.e($buyer['order_no']??'').'</td><td align="right"><b>Meal / delivery</b><br>'.e($buyer['slot']??'').(!empty($buyer['delivery_date'])?'<br>'.e(date('j M Y',strtotime($buyer['delivery_date']))):'').'</td></tr></table>';
        if($credit&&!empty($payment['original_number']))$html.='<p>Original bill: '.e($payment['original_number']).'</p>';
        $address=$buyer['delivery_address']??[];$delivery=($address['fulfilment']??'')==='Collection'?'Collection':implode(', ',array_unique(array_filter(array_map(fn($k)=>$address[$k]??'', ['line1','line2','landmark','area','city','state','country','pincode']))));
        $html.='<h3>Customer &amp; delivery</h3><p><b>'.e($buyer['name']??'').'</b><br>'.e($buyer['phone']??'').'<br>'.e($delivery).'</p>';
        foreach(['business_name'=>'Business','gstin'=>'GSTIN','billing_address'=>'Billing address'] as $key=>$label)if(!empty($buyer[$key]))$html.='<p>'.e($label).': '.nl2br(e($buyer[$key])).'</p>';
        $html.='<table cellpadding="7" border="1"><thead><tr style="background-color:#f5f1ea"><th width="72%"><b>'.($credit?'Credited items':'Your order').'</b></th><th width="28%" align="right"><b>Amount</b></th></tr></thead><tbody>';
        foreach($invoice['lines'] as $line){$amount=Money::parse($line['taxable'])+Money::parse($line['tax']);$html.='<tr><td width="72%"><b>'.e($line['description']).'</b><br>'.e($line['quantity'].' × ₹'.$line['unit_price']);if(!empty($line['sac']))$html.='<br>SAC / HSN: '.e($line['sac']);if($regular)$html.='<br>Taxable ₹'.e($line['taxable']).' · GST '.e($line['tax_rate']).'%: ₹'.e($line['tax']);if(Money::parse((string)($line['discount']??'0')))$html.='<br>Discount ₹'.e($line['discount']);$html.='</td><td width="28%" align="right">₹'.e(Money::decimal($amount)).'</td></tr>';}
        $html.='</tbody></table><br><table cellpadding="5">';$summary=['taxable'=>$regular?'Taxable value':'Subtotal'];if($regular)$summary+=['cgst'=>'CGST','sgst'=>'SGST','igst'=>'IGST'];$summary['round_off']='Round off';
        foreach($summary as $key=>$label)$html.='<tr><td width="72%">'.e($label).'</td><td width="28%" align="right">₹'.e($invoice[$key]).'</td></tr>';
        $totalLabel=$credit?'Credit total':(!empty($payment['payment_refunded'])?'Original total':($payment['payment_received']?'Total paid':'Total payable'));$html.='<tr style="background-color:#f5f1ea"><td><b>'.e($totalLabel).'</b></td><td align="right"><b>₹'.e($invoice['total']).'</b></td></tr></table><p>'.e($invoice['amount_words']).'</p>';
        if(!$credit&&!$payment['payment_received']&&empty($payment['payment_refunded']))$html.='<p><b>Amount due: ₹'.e($payment['amount_due']).' — payment not received</b></p>';
        if(!$credit)$html.='<p>Payment: '.e(['manual'=>'Manual payment','cod'=>'Cash on delivery','online'=>'Online payment'][$invoice['payment_mode']]??$invoice['payment_mode']).'</p>';
        $reference=$credit?$invoice['payment_ref']:$payment['settlement_reference'];if($reference!=='')$html.='<p>'.($credit?'Reason':'Reference').': '.e($reference).'</p>';
        if($buyer['courier_deferred']??false)$html.='<p>Courier charges are payable separately after dispatch.</p>';
        if(($seller['gst_mode']??'')==='composition')$html.='<p>Composition taxable person, not eligible to collect tax on supplies.</p>';
        $html.='<p>'.nl2br(e($seller['footer']??'')).'</p><p>Authorised signatory</p><hr><p><b>'.e($seller['name']).'</b><br>'.nl2br(e($seller['address'])).'<br>'.e(($seller['state']??'').' · State code '.($seller['state_code']??'')).'<br>FSSAI: '.e($seller['fssai_no']??'');if(!empty($seller['gstin']))$html.='<br>GSTIN: '.e($seller['gstin']);$html.='</p>';
        return self::document(ucwords(str_replace('_',' ',$invoice['kind'])).' '.$invoice['number'],$html,false);
    }
    public static function test(array $order): string {
        $html='<p>TEST / SIMULATED PAYMENT / NOT AN INVOICE</p><p>No real money collected. No financial invoice number allocated.</p><p>'.e($order['order_no']).' · '.e($order['address']['recipient_name']??'').'</p>';
        foreach($order['items'] as $line)$html.='<p>'.e($line['quantity'].' × '.$line['name'].' — ₹'.$line['line_total']).'</p>';
        $html.='<p>Delivery: ₹'.e($order['delivery_fee']).'<br>Simulated total: ₹'.e($order['total']).'</p>';
        return self::document('TEST receipt — NOT AN INVOICE',$html);
    }
}
