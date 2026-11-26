<?php declare(strict_types=1); namespace Annam; $bill=ReceiptPresentation::details($invoice,$payment);$kind=['bill'=>'Bill','tax_invoice'=>'Tax invoice','bill_of_supply'=>'Bill of supply','credit_note'=>'Credit note'][$invoice['kind']]??'Bill'; ?>
<article class="af-receipt" aria-label="<?= e($kind.' '.$invoice['number']) ?>">
  <header class="af-receipt-head">
    <?php if($bill['logo_url']):?><img class="af-receipt-logo" src="<?= e($bill['logo_url']) ?>" alt="<?= e($seller['name']) ?> logo" width="120" height="80"><?php endif;?>
    <h2><?= e($seller['name']) ?></h2>
    <?php if($bill['tagline']):?><p class="af-receipt-tagline"><?= e($bill['tagline']) ?></p><?php endif;?>
    <?php if($invoice['kind']!=='bill'):?><h3 class="af-document-title"><?= e($kind) ?></h3><?php endif;?>
    <?php if($bill['is_credit']):?><span class="af-receipt-badge af-receipt-credit">Credit note issued</span><?php elseif($bill['payment_refunded']):?><span class="af-receipt-badge">Payment refunded</span><?php elseif($bill['payment_received']):?><span class="af-receipt-badge">✓ Payment received</span><?php elseif($bill['cash_on_delivery']):?><span class="af-receipt-badge">Cash on delivery</span><?php else:?><span class="af-receipt-badge">UNPAID — payment not received</span><?php endif;?>
  </header>
  <dl class="af-receipt-meta">
    <div><dt><?= e($kind) ?> number</dt><dd><?= e($invoice['number']) ?></dd></div>
    <div><dt>Issued</dt><dd><?= e(date('j M Y, g:i A',strtotime($invoice['issued_at']))) ?></dd></div>
    <div><dt>Order / meal</dt><dd><?= e($buyer['order_no']??'') ?><?php if($buyer['slot']??''):?> · <?= e($buyer['slot']) ?><?php endif;?></dd></div>
    <?php if($bill['is_credit']&&!empty($invoice['original_id'])):?><div><dt>Original bill</dt><dd><?= e($payment['original_number']??'') ?></dd></div><?php endif;?>
  </dl>
  <section class="af-receipt-customer" aria-label="Customer and delivery">
    <h3>Customer &amp; delivery</h3>
    <?php if($buyer['name']??''):?><p class="af-customer-name"><?= e($buyer['name']) ?></p><?php endif;?>
    <?php if($buyer['phone']??''):?><p><?= e($buyer['phone']) ?></p><?php endif;?>
    <?php if($buyer['business_name']??''):?><p><?= e($buyer['business_name']) ?></p><?php endif;?>
    <?php if($buyer['billing_address']??''):?><p><?= nl2br(e($buyer['billing_address'])) ?></p><?php endif;?>
    <?php if($buyer['gstin']??''):?><p>GSTIN: <?= e($buyer['gstin']) ?></p><?php endif;?>
    <?php if($bill['collection']):?><p class="af-fulfilment">Collection</p><?php endif;?><?php if($bill['address_lines']):?><p class="af-delivery-address"><?= e(implode(', ',$bill['address_lines'])) ?></p><?php endif;?>
    <?php if($bill['delivery_date']):?><p class="af-delivery-date"><?= $bill['collection']?'Collection':'Delivery' ?>: <?= e(date('j M Y',strtotime($bill['delivery_date']))) ?></p><?php endif;?>
  </section>
  <table class="af-receipt-items">
    <caption class="af-visually-hidden"><?= e($kind) ?> item details</caption>
    <thead><tr><th scope="col"><?= $bill['is_credit']?'Credited items':'Your order' ?></th><th scope="col">Amount</th></tr></thead>
    <tbody><?php foreach($bill['lines'] as $line):?>
      <tr><td><strong><?= e($line['description']) ?></strong><span class="af-item-detail"><?= $bill['is_credit']?'Original order: ':'' ?><?= e($line['quantity']) ?> × <?= e(ReceiptPresentation::amount($line['unit_price'])) ?><?php if($line['sac']??''):?><span class="af-item-sac"> · SAC / HSN: <?= e($line['sac']) ?></span><?php endif;?></span>
        <?php if($line['discount_amount']):?><span class="af-item-detail">Discount: <?= e(ReceiptPresentation::amount(Money::decimal($line['discount_amount']))) ?></span><?php endif;?>
        <?php if($bill['tax_registered']):?><span class="af-item-detail">Taxable: <?= e(ReceiptPresentation::amount($line['taxable'])) ?> · GST <?= e($line['tax_rate']) ?>%: <?= e(ReceiptPresentation::amount($line['tax'])) ?></span><?php endif;?>
      </td><td><?= e(ReceiptPresentation::amount($line['amount'])) ?></td></tr>
    <?php endforeach;?></tbody>
  </table>
  <dl class="af-receipt-summary">
    <div><dt><?= $bill['tax_registered']?'Taxable value':'Subtotal' ?></dt><dd><?= e(ReceiptPresentation::amount($invoice['taxable'])) ?></dd></div>
    <?php if($bill['discount']&&!$bill['is_credit']):?><div><dt>Discount included above</dt><dd><?= e(ReceiptPresentation::amount(Money::decimal($bill['discount']))) ?></dd></div><?php endif;?>
    <?php if($bill['tax_registered']):foreach(['cgst','sgst','igst'] as $tax):?><div><dt><?= e(strtoupper($tax)) ?></dt><dd><?= e(ReceiptPresentation::amount($invoice[$tax])) ?></dd></div><?php endforeach;endif;?>
    <div><dt>Round off</dt><dd>₹<?= e(Money::signedDecimal(Money::signedParse((string)$invoice['round_off']))) ?></dd></div>
  </dl>
  <div class="af-receipt-total"><span><?= $bill['is_credit']?'Credit total':($bill['payment_received']?'Total paid':'Total payable') ?></span><strong><?= e(ReceiptPresentation::amount($invoice['total'])) ?></strong></div>
  <?php if($bill['issued_unpaid']&&!$bill['payment_received']&&!$bill['payment_refunded']):?><p class="af-receipt-notice"><strong>Amount due: <?= e(ReceiptPresentation::amount($bill['amount_due'])) ?>. <?= $bill['cash_on_delivery']?'Cash on delivery.':'Payment has not been received.' ?></strong></p><?php endif;?>
  <?php if(!$bill['is_credit']):?><p class="af-receipt-notice"><?= !empty($buyer['courier_deferred'])?'Courier charges are not included in this food bill. They are confirmed and payable separately after dispatch.':'Delivery fees shown above are included in the total '.($bill['payment_received']?'paid':'payable').'.' ?></p><?php endif;?>
  <p class="af-receipt-words"><?= e($invoice['amount_words']) ?></p>
  <div class="af-receipt-payment">
    <?php if(!$bill['is_credit']):?><p>Payment: <?= e($bill['payment_label']) ?></p><?php endif;?>
    <?php if($bill['settlement_reference']):?><p><?= $bill['is_credit']?'Reason':'Reference' ?>: <?= e($bill['settlement_reference']) ?></p><?php endif;?>
  </div>
  <?php if(($seller['gst_mode']??'')==='composition'):?><p class="af-receipt-notice">Composition taxable person, not eligible to collect tax on supplies.</p><?php endif;?>
  <footer class="af-receipt-footer">
    <?php if(!$bill['is_credit']):?><h3>Thank you for ordering with us!</h3><?php endif;?>
    <?php if($seller['footer']??''):?><p><?= nl2br(e($seller['footer'])) ?></p><?php endif;?>
    <p class="af-receipt-signature">Authorised signatory</p>
    <div class="af-receipt-legal"><p><strong><?= e($seller['name']) ?></strong> · <?= nl2br(e($seller['address'])) ?></p><p><?= e($seller['state']) ?> · State code <?= e($seller['state_code']) ?><br>FSSAI: <?= e($seller['fssai_no']) ?><?php if($seller['gstin']??''):?><br>GSTIN: <?= e($seller['gstin']) ?><?php endif;?></p></div>
  </footer>
</article>
