<?php
defined('ABSPATH') || exit;

add_action('woocommerce_product_options_general_product_data', function () {
    woocommerce_wp_select(['id' => '_seer_fulfilment', 'label' => 'Fulfilment', 'options' => [
        'packaged_goods' => 'Packaged goods — stock based', 'scheduled_meal' => 'Scheduled meal — date and slot based'
    ]]);
});
add_action('woocommerce_admin_process_product_object', function ($product) {
    $kind = sanitize_key(wp_unslash($_POST['_seer_fulfilment'] ?? 'packaged_goods'));
    $product->update_meta_data('_seer_fulfilment', $kind === 'scheduled_meal' ? $kind : 'packaged_goods');
});
add_filter('woocommerce_product_add_to_cart_text',function($text,$product){return $product->is_in_stock()?$text:'View product';},10,2);

function seer_cart_validate(int $id, $quantity): void {
    if (!is_numeric($quantity) || (int) $quantity != $quantity || $quantity < 1 || $quantity > 99) {
        throw new InvalidArgumentException('Quantity must be a whole number between 1 and 99.');
    }
    $raw = WC()->session->get('seer_context', []);
    $context = $raw ? Seer_Kitchen::context($raw) : [];
    Seer_Kitchen::quote($id, (int) $quantity, $context);
}
add_filter('woocommerce_add_to_cart_validation', function ($passed, $id, $quantity, $variation_id = 0) {
    try {
        $id = $variation_id ?: $id;
        $total = $quantity;
        foreach (WC()->cart->get_cart() as $line) if ((int) ($line['variation_id'] ?: $line['product_id']) === (int) $id) $total += $line['quantity'];
        seer_cart_validate($id, $total);
    } catch (InvalidArgumentException $e) {
        wc_add_notice($e->getMessage(), 'error');
        return false;
    }
    return $passed;
}, 10, 4);
add_filter('woocommerce_update_cart_validation', function ($passed, $key, $line, $quantity) {
    try { if ($quantity != 0) seer_cart_validate($line['variation_id'] ?: $line['product_id'], $quantity); }
    catch (InvalidArgumentException $e) { wc_add_notice($e->getMessage(), 'error'); return false; }
    return $passed;
}, 10, 4);
add_action('woocommerce_store_api_validate_add_to_cart', function ($product, $request) {
    $quantity = $request['quantity'] ?? 1;
    $total = $quantity;
    foreach (WC()->cart->get_cart() as $line) if ((int) ($line['variation_id'] ?: $line['product_id']) === $product->get_id()) $total += $line['quantity'];
    try { seer_cart_validate($product->get_id(), $total); }
    catch (InvalidArgumentException $e) { throw new Automattic\WooCommerce\StoreApi\Exceptions\RouteException('seer_delivery', $e->getMessage(), 400); }
}, 10, 2);
add_action('woocommerce_store_api_validate_cart_item', function ($product, $line) {
    try { seer_cart_validate($product->get_id(), $line['quantity']); }
    catch (InvalidArgumentException $e) { throw new Automattic\WooCommerce\StoreApi\Exceptions\RouteException('seer_delivery', $e->getMessage(), 400); }
}, 10, 2);

add_action('woocommerce_before_calculate_totals', function ($cart) {
    if (is_admin() && !wp_doing_ajax()) return;
    $context = WC()->session->get('seer_context', []);
    try { if ($context) $context = Seer_Kitchen::context($context); }
    catch (InvalidArgumentException $e) { $context = []; }
    foreach ($cart->get_cart() as $line) {
        try {
            // Fetch a fresh product on every calculation: do not re-use a price
            // already mutated for another date or accept session/client prices.
            $price = Seer_Kitchen::quote($line['variation_id'] ?: $line['product_id'], $line['quantity'], $context);
            $line['data']->set_price($price);
        } catch (InvalidArgumentException $e) {
            if (!wc_has_notice($e->getMessage(), 'error')) wc_add_notice($e->getMessage(), 'error');
        }
    }
}, 20);
add_action('woocommerce_cart_calculate_fees', function ($cart) {
    $zone = WC()->session->get('seer_zone', []);
    $context = WC()->session->get('seer_context', []);
    if (!$zone || !$context) return;
    try {
        $context = Seer_Kitchen::context($context);
        $zone = Seer_Kitchen::zone($zone['pincode'], (int) $zone['id'], $context['slot_id'])[0];
        $cart->add_fee('Local delivery — ' . $zone['area'], $zone['fee']);
        if (bccomp((string) $cart->get_subtotal(), $zone['minimum_order'], 2) < 0) {
            wc_add_notice('The minimum order for this area is ₹' . $zone['minimum_order'] . '.', 'notice');
        }
    } catch (InvalidArgumentException $e) { WC()->session->__unset('seer_zone'); }
});

add_action('template_redirect', function () {
    if (function_exists('is_checkout') && is_checkout()) {
        wp_die('This storefront is being reviewed. Checkout is not open yet.', 'Store preview', ['response' => 403]);
    }
    if (empty($_POST['seer_action'])) return;
    if (!isset($_POST['_wpnonce']) || !wp_verify_nonce(sanitize_text_field(wp_unslash($_POST['_wpnonce'])), 'seer_delivery')) {
        wp_die('Refresh the page and try again.', 'Invalid request', ['response' => 403]);
    }
    try {
        if ($_POST['seer_action'] === 'context') {
            Seer_Kitchen::persist_context(['date' => sanitize_text_field(wp_unslash($_POST['date'] ?? '')), 'slot' => sanitize_key($_POST['slot'] ?? '')]);
            wc_add_notice('Delivery window updated.', 'success');
        } elseif ($_POST['seer_action'] === 'pincode') {
            $context = WC()->session->get('seer_context', []);
            $rows = Seer_Kitchen::zone(sanitize_text_field(wp_unslash($_POST['pincode'] ?? '')), absint($_POST['zone_id'] ?? 0), $context['slot_id'] ?? 0);
            if (count($rows) > 1 && empty($_POST['zone_id'])) {
                WC()->session->set('seer_zone_choices', $rows);
                wc_add_notice('Choose your delivery area below.', 'notice');
            } else {
                WC()->session->set('seer_zone', $rows[0]);
                WC()->session->__unset('seer_zone_choices');
                wc_add_notice('Delivery is available in ' . $rows[0]['area'] . '.', 'success');
            }
        }
    } catch (InvalidArgumentException $e) { wc_add_notice($e->getMessage(), 'error'); }
    wp_safe_redirect(wp_get_referer() ?: wc_get_cart_url());
    exit;
}, 5);

// Block both authenticated and guest order-creation routes and REST writes.
add_filter('rest_pre_dispatch', function ($result, $server, $request) {
    $route = $request->get_route();
    if (!in_array($request->get_method(), ['GET', 'HEAD', 'OPTIONS'], true) &&
        preg_match('#^/wc/(?:store/v\d+/(?:checkout|batch)|v\d+/orders|v\d+/batch)(?:/|$)#', $route)) {
        return new WP_Error('seer_preview', 'Checkout and orders are disabled during storefront review.', ['status' => 403]);
    }
    return $result;
}, 5, 3);
add_action('woocommerce_checkout_process', function () { wc_add_notice('Checkout is not open during storefront review.', 'error'); });
add_action('woocommerce_before_checkout_process', function () { throw new Exception('Checkout is disabled during storefront review.'); });
add_filter('woocommerce_available_payment_gateways', '__return_empty_array');
add_action('wp_loaded', function () {
    if (isset($_GET['wc-ajax']) && sanitize_key($_GET['wc-ajax']) === 'checkout') {
        wp_send_json(['result' => 'failure', 'messages' => 'Checkout is not open yet.'], 403);
    }
}, 1);
add_action('woocommerce_before_checkout_form', function () { echo '<p>Checkout is not open yet.</p>'; });
add_action('init', function () {
    remove_action('woocommerce_proceed_to_checkout', 'woocommerce_button_proceed_to_checkout', 20);
    add_action('woocommerce_proceed_to_checkout', function () {
        echo '<div class="seer-preview-note">Store preview · Checkout opens after payment and delivery setup.</div>';
    }, 20);
});

add_action('woocommerce_blocks_loaded', function () {
    if (function_exists('woocommerce_store_api_register_endpoint_data')) {
        woocommerce_store_api_register_endpoint_data([
            'endpoint'=>Automattic\WooCommerce\StoreApi\Schemas\V1\CartSchema::IDENTIFIER,
            'namespace'=>'seerkitchen',
            'data_callback'=>function(){
                $c=WC()->session->get('seer_context',[]);$z=WC()->session->get('seer_zone',[]);
                return ['date'=>$c['date']??'','slot'=>$c['slot']??'','pincode'=>$z['pincode']??'','area'=>$z['area']??'','preview'=>true];
            },
            'schema_callback'=>fn()=>[
                'date'=>['type'=>'string','readonly'=>true], 'slot'=>['type'=>'string','readonly'=>true],
                'pincode'=>['type'=>'string','readonly'=>true], 'area'=>['type'=>'string','readonly'=>true],
                'preview'=>['type'=>'boolean','readonly'=>true]
            ],
            'schema_type'=>ARRAY_A
        ]);
    }
    if (function_exists('woocommerce_store_api_register_update_callback')) {
        woocommerce_store_api_register_update_callback([
            'namespace' => 'seerkitchen',
            'callback' => function ($data) {
                try {
                if (($data['action'] ?? '') === 'context') Seer_Kitchen::persist_context($data);
                elseif (($data['action'] ?? '') === 'pincode') {
                    $context = WC()->session->get('seer_context', []);
                    $rows = Seer_Kitchen::zone((string) ($data['pincode'] ?? ''), absint($data['zone_id'] ?? 0), $context['slot_id'] ?? 0);
                    if (count($rows) !== 1) throw new InvalidArgumentException('Choose a specific delivery area.');
                    WC()->session->set('seer_zone', $rows[0]);
                } else throw new InvalidArgumentException('Unknown delivery action.');
                } catch (InvalidArgumentException $e) { throw new Automattic\WooCommerce\StoreApi\Exceptions\RouteException('seer_delivery', $e->getMessage(), 400); }
            }
        ]);
    }
});

add_action('woocommerce_before_add_to_cart_form', 'seer_delivery_form');
add_action('woocommerce_before_cart', 'seer_delivery_form');
function seer_delivery_form(): void {
    static $shown=false;
    if (!function_exists('WC') || !WC()->session) return;
    if($shown)return;$shown=true;
    $slots = seer_slots();
    $context = WC()->session->get('seer_context', []);
    echo '<div class="seer-delivery"><h3>Your local delivery</h3>';
    if ($slots) {
        echo '<form method="post"><input type="hidden" name="seer_action" value="context">';
        wp_nonce_field('seer_delivery');
        echo '<label>Delivery date<select name="date">';
        $today = new DateTimeImmutable('today', wp_timezone());
        for ($i = 0; $i < (int) get_option('seer_booking_days', 2); $i++) {
            $date = $today->modify("+$i days");
            printf('<option value="%s" %s>%s</option>', esc_attr($date->format('Y-m-d')), selected($context['date'] ?? '', $date->format('Y-m-d'), false), esc_html($date->format('D, j M')));
        }
        echo '</select></label><label>Window<select name="slot">';
        foreach ($slots as $slot) printf('<option value="%s" %s>%s · %s–%s</option>', esc_attr($slot['slot_key']), selected($context['slot'] ?? '', $slot['slot_key'], false), esc_html($slot['label']), esc_html(substr($slot['delivery_from'],0,5)), esc_html(substr($slot['delivery_to'],0,5)));
        echo '</select></label><button type="submit">Set delivery</button></form>';
    } else echo '<p>Delivery windows are being configured. You can explore packaged goods and build a preview cart.</p>';
    echo '<form method="post"><input type="hidden" name="seer_action" value="pincode">';
    wp_nonce_field('seer_delivery');
    $zone = WC()->session->get('seer_zone', []);
    printf('<label>Pincode<input name="pincode" inputmode="numeric" pattern="[1-9][0-9]{5}" maxlength="6" required placeholder="Your six-digit pincode" value="%s"></label>', esc_attr($zone['pincode'] ?? ''));
    $choices = WC()->session->get('seer_zone_choices', []);
    if ($choices) {
        echo '<label>Area<select name="zone_id">';
        foreach ($choices as $choice) printf('<option value="%d">%s · ₹%s delivery</option>', $choice['id'], esc_html($choice['area']), esc_html($choice['fee']));
        echo '</select></label>';
    }
    echo '<button type="submit">Check delivery</button></form>';
    if ($zone) printf('<p>Available in %s · ₹%s delivery · minimum ₹%s</p>', esc_html($zone['area']), esc_html($zone['fee']), esc_html($zone['minimum_order']));
    echo '</div>';
}

add_filter('render_block', function ($content, $block) {
    if (in_array($block['blockName'], ['woocommerce/proceed-to-checkout-block','woocommerce/mini-cart-checkout-button-block'],true)) return '<p class="seer-preview-note">Store preview · Checkout opens soon.</p>';
    return $content;
}, 10, 2);

// Prevent manual, REST and custom-theme order creation too.
add_action('woocommerce_before_order_object_save', function ($order) {
    if (!$order->get_id()) throw new RuntimeException('Order creation is disabled during storefront review.');
});
