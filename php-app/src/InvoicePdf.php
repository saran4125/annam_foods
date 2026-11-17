<?php
declare(strict_types=1);
namespace Annam;

/** All amounts and legal details come from the issued immutable snapshot. */
final class InvoicePdf {
    private static function document(string $title,string $html): string {
        require_once ANNAM_ROOT.'/resources/vendor/tcpdf/tcpdf.php';
        $pdf=new \TCPDF();$pdf->setPrintHeader(false);$pdf->setPrintFooter(false);$pdf->SetCreator('Annam Foods');$pdf->SetTitle($title);$pdf->SetMargins(16,16,16);$pdf->SetAutoPageBreak(true,16);$pdf->SetFont('dejavusans','',10);$pdf->AddPage();$pdf->writeHTML('<h1>'.e($title).'</h1>'.$html);return $pdf->Output('receipt.pdf','S');
    }
    public static function invoice(array $invoice): string {
        $seller=$invoice['seller'];$buyer=$invoice['buyer'];$html='<h2>'.e($seller['name']).'</h2><p>'.nl2br(e($seller['address'])).'<br>'.e(($seller['state']??'').' · State code '.($seller['state_code']??'')).'<br>GSTIN: '.e($seller['gstin']??'').' · FSSAI: '.e($seller['fssai_no']??'').'</p>';
        $html.='<p>Issued: '.e($invoice['issued_at']).'<br>Order: '.e($buyer['order_no']??'').'<br>'.e($buyer['name']??'').'<br>'.e($buyer['phone']??'').'<br>'.e($buyer['business_name']??'').'<br>'.e($buyer['gstin']??'').'<br>'.nl2br(e($buyer['billing_address']??'')).'<br>'.e(implode(', ',array_filter(array_intersect_key($buyer['delivery_address']??[],array_flip(['line1','line2','landmark','city','state','country','pincode']))))).'</p><table cellpadding="6" border="1"><thead><tr><th width="72%">Items</th><th width="28%">Amount</th></tr></thead><tbody>';
        foreach($invoice['lines'] as $line){$amount=Money::parse($line['taxable'])+Money::parse($line['tax']);$html.='<tr><td>'.e($line['description']).'<br>'.e($line['quantity'].' × ₹'.$line['unit_price']).'<br>SAC / HSN: '.e($line['sac']??'').'<br>Taxable ₹'.e($line['taxable']).' · GST '.e($line['tax_rate']).'%: ₹'.e($line['tax']).'<br>Discount ₹'.e($line['discount']??'0.00').'</td><td>₹'.e(Money::decimal($amount)).'</td></tr>';}
        foreach(['taxable'=>'Taxable value','cgst'=>'CGST','sgst'=>'SGST','igst'=>'IGST','round_off'=>'Round off','total'=>'Total paid'] as $key=>$label)$html.='<tr><td>'.e($label).'</td><td>₹'.e($invoice[$key]).'</td></tr>';
        $html.='</tbody></table><p>'.e($invoice['amount_words']).'</p><p>Payment: '.e($invoice['payment_mode']).'<br>Reference: '.e($invoice['payment_ref']).'</p>';
        if($buyer['courier_deferred']??false)$html.='<p>Courier charges are payable separately after dispatch.</p>';
        if(($seller['gst_mode']??'')==='composition')$html.='<p>Composition taxable person, not eligible to collect tax on supplies.</p>';
        $html.='<p>'.nl2br(e($seller['footer']??'')).'</p><p>Authorised signatory</p>';
        return self::document(ucwords(str_replace('_',' ',$invoice['kind'])).' '.$invoice['number'],$html);
    }
    public static function test(array $order): string {
        $html='<p>TEST / SIMULATED PAYMENT / NOT AN INVOICE</p><p>No real money collected. No financial invoice number allocated.</p><p>'.e($order['order_no']).' · '.e($order['address']['recipient_name']??'').'</p>';
        foreach($order['items'] as $line)$html.='<p>'.e($line['quantity'].' × '.$line['name'].' — ₹'.$line['line_total']).'</p>';
        $html.='<p>Delivery: ₹'.e($order['delivery_fee']).'<br>Simulated total: ₹'.e($order['total']).'</p>';
        return self::document('TEST receipt — NOT AN INVOICE',$html);
    }
}
