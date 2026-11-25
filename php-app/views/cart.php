<?php declare(strict_types=1); namespace Annam; $title='Your cart · '.$store->name(); $price=fn(int $minor)=>money(Money::decimal($minor)); ?>
<section class="wrap php-cart-page"><div class="page-intro"><p class="section-kicker">Kitchen order</p><h1>Your order</h1><p>Review your dishes and check whether we deliver to your area.</p></div><?php if (!$quote['lines']): ?><div class="empty-cart"><span class="empty-mark"><svg class="ic"><use href="#i-bag"/></svg></span><p>Nothing here yet.</p><?php $recent=(new Checkout($store))->recentOrder();if($recent): $recentOrder=$recent['order']; ?><section class="recent-order" aria-label="Your recent order"><h2>Your recent order</h2><p><strong><?= e($recentOrder['order_no']) ?></strong> · <?= e(ucfirst(str_replace('_',' ',$recentOrder['status']))) ?> · <?= e(ucfirst(str_replace('_',' ',$recentOrder['payment_status']))) ?></p><?php foreach($recentOrder['items'] as $recentLine): ?><p><?= e($recentLine['quantity'].' × '.$recentLine['name']) ?></p><?php endforeach; ?><p>Total: <?= money($recentOrder['total']) ?></p><p><a class="btn" href="/checkout/complete/<?= e($recent['reference']) ?>/">View your recent order</a></p></section><?php endif; ?><a class="btn btn-primary" href="/menu/">Browse today’s menu →</a></div><?php else: ?>
<?php $isMeal=($quote['cart']['kind']??'')==='scheduled'; $pin=(string)($_POST['pincode']??($_SESSION['cart']['pincode']??'')); $areaId=(string)($_POST['area_id']??($_SESSION['cart']['zone_id']??'')); $matchingAreas=array_values(array_filter($areas,fn($area)=>$area['pincode']===$pin)); ?>
<div class="cart-layout">
  <div class="cart-main">
    <p class="cart-context"><?php if($isMeal):?><strong><?= e(implode(' + ',array_map('ucfirst',$quote['meal_keys']))) ?></strong> · <?= e((new \DateTimeImmutable($quote['cart']['date']))->format('D, j M')) ?><?php else:?><strong>Shop order</strong> · shipped to your door<?php endif;?></p>
    <ul class="cart-lines">
    <?php foreach($quote['lines'] as $line):?>
      <li class="cart-line">
        <span class="line-thumb"><?php if($line['item']['image']):?><img src="<?= e(image_url($line['item']['image'])) ?>" alt="" width="120" height="120"><?php else:?><span class="dish-tile"><?= e(mb_substr($line['item']['name'],0,1)) ?></span><?php endif;?></span>
        <div class="line-info"><div class="dish-title"><span class="veg <?= !$line['item']['is_veg']?'veg-no':'' ?>" aria-label="<?= $line['item']['is_veg']?'Vegetarian':'Non-vegetarian' ?>"></span><strong><?= e($line['item']['name']) ?></strong><?php if($isMeal):?><span class="line-meal"><?= e($line['meal_label']) ?></span><?php endif;?></div><span class="line-unit"><?= $price($line['unit']) ?> each</span></div>
        <form class="qty-form" method="post" action="/cart/update/"><?= csrf() ?><input type="hidden" name="item_id" value="<?= e($line['key']) ?>"><button name="quantity" value="<?= e($line['quantity']-1) ?>" aria-label="<?= e('One fewer '.$line['item']['name']) ?>"><svg class="ic"><use href="#i-minus"/></svg></button><span aria-label="Quantity"><?= e($line['quantity']) ?></span><button name="quantity" value="<?= e($line['quantity']+1) ?>" <?= $line['quantity']>=99?'disabled':'' ?> aria-label="<?= e('One more '.$line['item']['name']) ?>"><svg class="ic"><use href="#i-plus"/></svg></button></form>
        <span class="money"><?= $price($line['amount']) ?></span>
      </li>
    <?php endforeach;?>
    </ul>
    <form class="fresh-form" method="post" action="/cart/clear/"><?= csrf() ?><button class="link-like" type="submit">Start a fresh order</button></form>
    <a class="arrow-link more-link" href="<?= $isMeal?'/menu/':'/shop/' ?>">Add more items <svg class="ic"><use href="#i-arrow"/></svg></a>
  </div>
  <aside class="cart-side" data-pincode-side>
    <section class="pincode-box">
      <h2>Where are we delivering?</h2>
      <form method="post" action="/cart/" <?= $isMeal?'data-pincode-form':'' ?>><?= csrf() ?>
        <?php if(!$isMeal):?><label>City<input name="city" value="<?= e($_POST['city']??'') ?>" required></label><label>Country<input name="country" value="<?= e($_POST['country']??'India') ?>" required></label><?php endif;?>
        <input name="pincode" value="<?= e($pin) ?>" pattern="[1-9][0-9]{5}" maxlength="6" inputmode="numeric" autocomplete="postal-code" placeholder="6-digit pincode" aria-label="Delivery pincode" required>
        <?php if(count($matchingAreas)>1):?><select name="area_id" aria-label="Your area"><option value="">Choose your area</option><?php foreach($matchingAreas as $area):?><option value="<?= e($area['id']) ?>" <?= $areaId===(string)$area['id']?'selected':'' ?>><?= e($area['area_name']) ?></option><?php endforeach;?></select><?php endif;?>
        <button class="btn" type="submit">Check</button>
      </form>
      <p data-pincode-feedback role="status" aria-live="polite"></p>
      <?php if($error):?><p class="php-error" role="alert"><?= e($error) ?></p><?php elseif($delivery):?><p class="ok php-success"><?= ($delivery['deferred']??false)?e(Delivery::COURIER):'Delivery available · '.$price($delivery['fee']).' delivery' ?></p><?php endif;?>
    </section>
    <p class="checkout-note"><?= $isMeal?'Delivery pincode is required. Meals are delivered only within the kitchen’s delivery zones.':'Local delivery uses the selected area’s charge. Courier charges are confirmed separately after dispatch.' ?> The final total, including applicable tax, is shown at checkout.</p>
    <div class="totals"><div><span>Subtotal</span><span><?= $price($quote['subtotal']) ?></span></div><div><span>Delivery charge</span><span><?= $delivery?$price($delivery['fee']):'Enter delivery pincode' ?></span></div><div class="grand"><span><?= $delivery?'Total':'Items total' ?></span><span><?= $price($quote['subtotal']+($delivery['fee']??0)) ?></span></div></div>
    <div class="checkout-row"><?php if($isMeal&&!$delivery):?><button class="btn btn-primary" data-testid="checkout" disabled>Enter your pincode to continue</button><?php else:?><a class="btn btn-primary" href="/checkout/" data-testid="checkout">Continue to checkout <svg class="ic"><use href="#i-arrow"/></svg></a><?php endif;?></div>
  </aside>
</div>
<?php endif; ?></section>
