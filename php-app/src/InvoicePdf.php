<?php
declare(strict_types=1);
namespace Annam;

/** All amounts and legal details come from the issued immutable snapshot. */
final class InvoicePdf {
    private static function logo(string $source):?string {
        if($source==='/static/branding/annam-bill-logo.png')$source='/media/brand/annam-bill-logo.png';
        $file=Media::file($source)??Media::file('brand/annam-bill-logo.png');
        $file??=ANNAM_ROOT.'/resources/public-files/brand/annam-bill-logo.png';
        if(!is_readable($file))return null;
        $data=file_get_contents($file);
        // Stock PHP hosts may not have GD/Imagick. The bundled print logo has
        // an opaque background, so TCPDF can embed it without those extensions.
        if(!function_exists('imagecreatefrompng')&&!class_exists('Imagick')&&str_starts_with($data,"\x89PNG")&&(in_array(ord($data[25]),[4,6],true)||str_contains($data,'tRNS')))$data=file_get_contents(ANNAM_ROOT.'/resources/public-files/brand/annam-bill-logo-print.jpg');
        return '@'.base64_encode($data);
    }
    private static function document(string $title,string $html,bool $heading=true): string {
        require_once ANNAM_ROOT.'/resources/vendor/tcpdf/tcpdf.php';
        $pdf=new \TCPDF();$pdf->setPrintHeader(false);$pdf->setPrintFooter(false);$pdf->SetCreator('Annam Foods');$pdf->SetTitle($title);$pdf->SetMargins(16,16,16);$pdf->SetAutoPageBreak(true,16);$pdf->SetFont('dejavusans','',10);$pdf->AddPage();$pdf->writeHTML(($heading?'<h1>'.e($title).'</h1>':'').$html);return $pdf->Output('receipt.pdf','S');
    }
    /** The same compact receipt hierarchy as templates/billing/_invoice_body.html. */
    private static function receipt(array $seller,string $title,string $badge,array $meta,string $customer,array $lines,array $totals,string $totalLabel,string $total,string $words,string $notes,bool $credit=false,string $tone='paid'):string {
        require_once ANNAM_ROOT.'/resources/vendor/tcpdf/tcpdf.php';
        $pdf=new \TCPDF();$pdf->setPrintHeader(false);$pdf->setPrintFooter(false);$pdf->SetCreator('Annam Foods');$pdf->SetTitle($title);
        $pdf->SetMargins(26,14,26);$pdf->SetAutoPageBreak(true,16);$pdf->SetFont('dejavusans','',8.5);$pdf->SetTextColor(40,33,27);$pdf->AddPage();
        $muted='#807166';$rule='border-bottom:0.5px solid #dfcdbb;';$dashed='border-bottom:0.5px dashed #cdb79f;';
        $logo=self::logo((string)($seller['logo_url']??''));
        $color=$tone==='paid'?'#176c38':'#885515';$bg=$tone==='paid'?'#e5f3e9':'#fff0d8';
        $html=($logo?'<p align="center"><img src="'.e($logo).'" width="66"></p>':'').'<h2 align="center" style="font-size:17pt;margin:0">'.e($seller['name']).'</h2>';
        if(!empty($seller['tagline']))$html.='<p align="center" style="font-size:7.5pt;color:'.$muted.'">'.e($seller['tagline']).'</p>';
        $html.='<p align="center"><span style="font-size:8pt;color:'.$color.';background-color:'.$bg.'"><b> '.e($badge).' </b></span></p><table cellpadding="3" width="100%" style="'.$dashed.'border-top:0.5px dashed #cdb79f">';
        foreach($meta as $label=>$value)$html.='<tr><td width="28%" style="font-size:7.5pt;color:'.$muted.'">'.e($label).'</td><td width="72%" align="right" style="font-size:7.5pt"><b>'.e($value).'</b></td></tr>';
        $html.='</table><br><b style="font-size:7pt;color:'.$muted.'">CUSTOMER &amp; DELIVERY</b><br>'.$customer.'<br><table cellpadding="4" width="100%"><thead><tr><th width="75%" style="'.$dashed.'font-size:7pt;color:'.$muted.'"><b>'.($credit?'CREDITED ITEMS':'YOUR ORDER').'</b></th><th width="25%" align="right" style="'.$dashed.'font-size:7pt;color:'.$muted.'"><b>AMOUNT</b></th></tr></thead><tbody>';
        foreach($lines as $line)$html.='<tr><td width="75%" style="'.$rule.'"><b>'.e($line['name']).'</b><br><span style="font-size:7.5pt;color:'.$muted.'">'.$line['detail'].'</span></td><td width="25%" align="right" style="'.$rule.'">₹'.e($line['amount']).'</td></tr>';
        $html.='</tbody></table><br><table cellpadding="3" width="100%">';
        foreach($totals as $label=>$amount)$html.='<tr><td width="75%">'.e($label).'</td><td width="25%" align="right"><b>₹'.e($amount).'</b></td></tr>';
        $html.='</table>';$pdf->writeHTML($html,true,false,true,false,'');
        if($pdf->GetY()>255)$pdf->AddPage();$y=$pdf->GetY();$pdf->SetDrawColor(246,198,146);$pdf->SetFillColor(255,241,221);$pdf->SetLineStyle(['width'=>.2,'dash'=>0]);$pdf->RoundedRect(26,$y,158,14,2,'1111','DF');
        $pdf->writeHTMLCell(154,0,28,$y+2,'<table cellpadding="3"><tr><td width="65%" style="font-size:10pt"><b>'.e($totalLabel).'</b></td><td width="35%" align="right" style="font-size:16pt"><b>₹'.e($total).'</b></td></tr></table>',0,1,false,true);
        $pdf->SetY(max($y+17,$pdf->GetY()));
        $after='<p align="center" style="font-size:7.5pt;color:'.$muted.'">'.e($words).'</p>'.$notes;
        if(!$credit)$after.='<h3 align="center" style="font-size:10pt">Thank you for ordering with us!</h3>';
        if(!empty($seller['footer']))$after.='<p align="center" style="font-size:7.5pt">'.nl2br(e($seller['footer'])).'</p>';
        $after.='<p align="center" style="font-size:7pt;color:'.$muted.'">Authorised signatory</p><table width="100%" cellpadding="4" style="border-top:0.5px dashed #cdb79f"><tr><td align="center" style="font-size:7pt;color:'.$muted.'"><b>'.e($seller['name']).'</b> · '.nl2br(e($seller['address']??''));
        if(!empty($seller['state']))$after.='<br>'.e($seller['state']).(!empty($seller['state_code'])?' · State code '.e($seller['state_code']):'');
        if(!empty($seller['fssai_no']))$after.='<br>FSSAI: '.e($seller['fssai_no']);if(!empty($seller['gstin']))$after.='<br>GSTIN: '.e($seller['gstin']);
        $after.='</td></tr></table>';$pdf->writeHTML($after,true,false,true,false,'');$last=$pdf->getPage();$bottom=$pdf->GetY()+5;
        // Frame every page, including long orders that naturally continue.
        for($page=1;$page<=$last;$page++){$pdf->setPage($page);$pdf->SetDrawColor(224,205,186);$pdf->SetLineStyle(['width'=>.25,'dash'=>0]);$pdf->RoundedRect(20,8,170,($page===$last?min(281,max(60,$bottom-8)):273),4,'1111','D');}
        return $pdf->Output('receipt.pdf','S');
    }
    private static function customer(array $buyer):string {
        $address=$buyer['delivery_address']??[];$html='<b>'.e($buyer['name']??'').'</b><br>'.e($buyer['phone']??'');
        foreach(['business_name','billing_address','gstin'] as $key)if(!empty($buyer[$key]))$html.='<br>'.nl2br(e($buyer[$key]));
        if(($address['fulfilment']??'')==='Collection')$html.='<br>Collection';
        $html.='<br>'.e(implode(', ',array_unique(array_filter(array_map(fn($k)=>$address[$k]??'', ['line1','line2','landmark','area','city','state','country','pincode'])))));
        if(!empty($buyer['delivery_date']))$html.='<br>Delivery: '.e(date('j M Y',strtotime($buyer['delivery_date'])));return $html;
    }
    public static function invoice(array $invoice, ?array $payment=null): string {
        $payment??=['payment_received'=>($invoice['buyer']['payment_status_at_issue']??'paid')!=='unpaid','payment_refunded'=>false,'amount_due'=>$invoice['total'],'settlement_reference'=>$invoice['payment_ref']];
        $seller=$invoice['seller'];$buyer=$invoice['buyer'];$credit=$invoice['kind']==='credit_note';$regular=($seller['gst_mode']??'')==='regular';$refunded=!empty($payment['payment_refunded']);
        $badge=$credit?'CREDIT NOTE ISSUED':($refunded?'PAYMENT REFUNDED':($payment['payment_received']?'✓ PAYMENT RECEIVED':($invoice['payment_mode']==='cod'?'CASH ON DELIVERY':'UNPAID — PAYMENT NOT RECEIVED')));
        $kind=['bill'=>'Bill','tax_invoice'=>'Tax invoice','bill_of_supply'=>'Bill of supply','credit_note'=>'Credit note'][$invoice['kind']]??'Bill';
        $meta=[$kind.' number'=>$invoice['number'],'Issued'=>date('j M Y, g:i A',strtotime($invoice['issued_at'])),'Order / meal'=>($buyer['order_no']??'').(!empty($buyer['slot'])?' · '.$buyer['slot']:'')];
        if($credit&&!empty($payment['original_number']))$meta['Original bill']=$payment['original_number'];$lines=[];
        foreach($invoice['lines'] as $line){$detail=e($line['quantity'].' × ₹'.$line['unit_price']);if(!empty($line['sac']))$detail.=' · SAC / HSN: '.e($line['sac']);if($regular)$detail.='<br>Taxable: ₹'.e($line['taxable']).' · GST '.e($line['tax_rate']).'%: ₹'.e($line['tax']);if(Money::parse((string)($line['discount']??'0')))$detail.='<br>Discount: ₹'.e($line['discount']);$lines[]=['name'=>$line['description'],'detail'=>$detail,'amount'=>Money::decimal(Money::parse($line['taxable'])+Money::parse($line['tax']))];}
        $totals=[$regular?'Taxable value':'Subtotal'=>$invoice['taxable']];if($regular)foreach(['cgst','sgst','igst'] as $key)$totals[strtoupper($key)]=$invoice[$key];$totals['Round off']=$invoice['round_off'];
        $notes='';if(!$credit&&!$payment['payment_received']&&!$refunded)$notes.='<p><b>Amount due: ₹'.e($payment['amount_due']).($invoice['payment_mode']==='cod'?' — cash on delivery</b></p>':' — payment not received</b></p>');
        if(!$credit)$notes.='<p align="center" style="font-size:7.5pt;color:#807166">Payment: '.e(['manual'=>'Manual payment','cod'=>'Cash on delivery','online'=>'Online payment'][$invoice['payment_mode']]??$invoice['payment_mode']).'</p>';
        $reference=$credit?$invoice['payment_ref']:$payment['settlement_reference'];if($reference!=='')$notes.='<p align="center" style="font-size:7.5pt;color:#807166">'.($credit?'Reason':'Reference').': '.e($reference).'</p>';
        if($buyer['courier_deferred']??false)$notes.='<p>Courier charges are payable separately after dispatch.</p>';
        if(($seller['gst_mode']??'')==='composition')$notes.='<p>Composition taxable person, not eligible to collect tax on supplies.</p>';
        return self::receipt($seller,$kind.' '.$invoice['number'],$badge,$meta,self::customer($buyer),$lines,$totals,$credit?'Credit total':($refunded?'Original total':($payment['payment_received']?'Total paid':'Total payable')),$invoice['total'],$invoice['amount_words'],$notes,$credit,$credit||$refunded||!$payment['payment_received']?'pending':'paid');
    }
    public static function summary(array $order,?Store $store=null):string {
        $profile=$store?->db->one('SELECT * FROM tenancy_billingprofile WHERE tenant_id=?',[$store->id()])??[];
        $seller=$profile+['name'=>$profile['legal_name']??$store?->name()??'Annam Foods','tagline'=>$store?->config['tagline']??'','logo_url'=>$store?->config['theme']['billing_logo_url']??($store?->logo()??''),'address'=>''];
        $buyer=['name'=>$order['address']['recipient_name']??'','phone'=>$order['address']['phone']??'','delivery_address'=>$order['address'],'delivery_date'=>$order['delivery_date']??''];$lines=[];
        foreach($order['items'] as $line)$lines[]=['name'=>$line['name'],'detail'=>e($line['quantity'].' × ₹'.$line['unit_price']),'amount'=>$line['line_total']];
        $adjustment=Money::parse($order['total'])-Money::parse($order['subtotal'])-Money::parse($order['delivery_fee']);$totals=['Items subtotal'=>$order['subtotal'],'Delivery charge'=>$order['delivery_fee'],'Tax, discounts & rounding'=>Money::signedDecimal($adjustment)];
        $pending=!in_array($order['payment_status'],['paid','refunded'],true);$notes='<p align="center">Not a tax invoice · No payment receipt implied</p>';
        if($pending)$notes.='<p><b>Payment not received — amount due ₹'.e($order['total']).'</b></p>';
        $notes.='<p align="center" style="font-size:7.5pt;color:#807166">The numbered invoice will be available once issued by the kitchen.</p>';
        return self::receipt($seller,'Order summary · '.$order['order_no'],'ORDER SUMMARY — '.strtoupper(str_replace('_',' ',$order['payment_status'])),['Order reference'=>$order['order_no'],'Order date'=>date('j M Y',strtotime($order['placed_at']))],self::customer($buyer),$lines,$totals,'Order total',$order['total'],Billing::words(Money::parse($order['total'])),$notes,false,'pending');
    }
    public static function test(array $order): string {
        $html='<p>TEST / SIMULATED PAYMENT / NOT AN INVOICE</p><p>No real money collected. No financial invoice number allocated.</p><p>'.e($order['order_no']).' · '.e($order['address']['recipient_name']??'').'</p>';
        foreach($order['items'] as $line)$html.='<p>'.e($line['quantity'].' × '.$line['name'].' — ₹'.$line['line_total']).'</p>';
        $html.='<p>Delivery: ₹'.e($order['delivery_fee']).'<br>Simulated total: ₹'.e($order['total']).'</p>';
        return self::document('TEST receipt — NOT AN INVOICE',$html);
    }
}
