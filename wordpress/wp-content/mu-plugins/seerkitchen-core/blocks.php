<?php
defined('ABSPATH') || exit;

add_action('init', function () {
    wp_register_script('seer-block-editor', plugins_url('seerkitchen-core/editor.js', dirname(SEER_CORE_DIR) . '/seerkitchen.php'), ['wp-blocks','wp-element','wp-block-editor','wp-components','wp-api-fetch'], '1.0', true);
    foreach (['hero','promotions','categories','daily-menu','delivery','announcement','contact'] as $name) {
        register_block_type('seerkitchen/'.$name,[
            'api_version'=>3, 'editor_script'=>'seer-block-editor',
            'attributes'=>[
                'items'=>['type'=>'array','default'=>[]],
                'title'=>['type'=>'string','default'=>''],
            ],
            'render_callback'=>fn($attrs)=>seer_render_block($name,$attrs),
        ]);
    }
});

function seer_render_block(string $name, array $attrs): string {
    if($name==='contact'){
        $phone=get_option('seer_phone','');$email=get_option('seer_email','');$fssai=get_option('seer_fssai','');$html='<div class="seer-contact">';
        if($phone)$html.='<p><a href="tel:'.esc_attr(preg_replace('/[^+0-9]/','',$phone)).'">'.esc_html($phone).'</a></p>';
        if($email)$html.='<p><a href="mailto:'.esc_attr($email).'">'.esc_html($email).'</a></p>';
        if($fssai)$html.='<p>FSSAI · '.esc_html($fssai).'</p>';
        return $html.'</div>';
    }
    if ($name === 'announcement') return '<div class="seer-announcement">'.esc_html(get_option('seer_notice','Made with care. Delivered close to home.')).'</div>';
    if ($name === 'delivery') { ob_start(); seer_delivery_form(); return ob_get_clean(); }
    if ($name === 'daily-menu') return seer_daily_menu();
    if ($name === 'categories') {
        $terms = get_terms(['taxonomy'=>'product_cat','hide_empty'=>true,'parent'=>0]);
        if (is_wp_error($terms)) return '';
        $html='<section class="seer-categories"><h2>'.esc_html($attrs['title']?:'Shop your favourites').'</h2><div class="seer-category-grid">';
        foreach($terms as $term) {
            if($term->slug==='uncategorized' || !get_term_meta($term->term_id,'thumbnail_id',true)) continue;
            $html.='<a href="'.esc_url(get_term_link($term)).'">'.wp_get_attachment_image(get_term_meta($term->term_id,'thumbnail_id',true),'medium_large',false,['loading'=>'lazy']).'<span>'.esc_html($term->name).'</span></a>';
        }
        return $html.'</div></section>';
    }
    $items=array_values(array_filter($attrs['items']??[],function($item){
        if (empty($item['image']) || !wp_attachment_is_image(absint($item['image']))) return false;
        $today=wp_date('Y-m-d');
        return (empty($item['start']) || $item['start'] <= $today) && (empty($item['end']) || $item['end'] >= $today);
    }));
    $items=array_slice($items,0,3);
    if(!$items) return '';
    $hero=$name==='hero';
    $html=$hero?'<section class="seer-hero" aria-label="Current offers" data-seer-slider>':'<section class="seer-promotions" aria-label="Explore the store">';
    foreach($items as $index=>$item){
        $image=absint($item['image']);
        $url=esc_url($item['url']??'');
        $alt=esc_attr($item['alt']??get_post_meta($image,'_wp_attachment_image_alt',true));
        $html.=$hero?'<div class="seer-slide'.($index===0?' is-active':'').'" data-seer-slide aria-hidden="'.($index===0?'false':'true').'">':'<div class="seer-promo">';
        if($url) $html.='<a href="'.$url.'" aria-label="'.$alt.'">';
        $html.='<picture>';
        if(!empty($item['mobile']) && wp_attachment_is_image(absint($item['mobile']))) $html.='<source media="(max-width: 600px)" srcset="'.esc_url(wp_get_attachment_image_url(absint($item['mobile']),'large')).'">';
        $html.=wp_get_attachment_image($image,'full',false,['alt'=>html_entity_decode($alt),'loading'=>$hero && $index===0?'eager':'lazy','fetchpriority'=>$hero && $index===0?'high':'auto']);
        $html.='</picture>';
        if(!$hero)$html.='<span class="seer-promo-caption">'.esc_html($item['alt']??'Explore').' <span aria-hidden="true">→</span></span>';
        $html.=($url?'</a>':'').'</div>';
    }
    if($hero && count($items)>1){
        $html.='<button class="seer-prev" type="button" aria-label="Previous offer">‹</button><button class="seer-next" type="button" aria-label="Next offer">›</button><div class="seer-dots">';
        foreach($items as $i=>$item) $html.='<button type="button" aria-label="Show offer '.($i+1).'" aria-pressed="'.($i===0?'true':'false').'" data-seer-dot="'.$i.'"></button>';
        $html.='</div><button class="seer-pause" type="button" aria-label="Pause slideshow" aria-pressed="false">Pause</button>';
    }
    return $html.'</section>';
}

function seer_daily_menu(): string {
    $slots=seer_slots();
    if(!$slots) return '<section class="seer-meals"><h2>From our kitchen</h2><p>Our daily meal menu is being prepared. Explore our sweets, snacks and pantry favourites in the meantime.</p></section>';
    $date=sanitize_text_field($_GET['meal_date']??wp_date('Y-m-d'));
    $key=sanitize_key($_GET['meal_slot']??$slots[0]['slot_key']);
    $html='<section class="seer-meals"><h2>Fresh meals, your way</h2><form method="get"><label>Date <input type="date" name="meal_date" value="'.esc_attr($date).'"></label><label>Window <select name="meal_slot">';
    foreach($slots as $slot) $html.='<option value="'.esc_attr($slot['slot_key']).'" '.selected($slot['slot_key'],$key,false).'>'.esc_html($slot['label']).'</option>';
    $html.='</select></label><button>Browse meals</button></form><div class="seer-meal-grid">';
    $slot=current(array_filter($slots,fn($s)=>$s['slot_key']===$key));
    $valid=DateTimeImmutable::createFromFormat('!Y-m-d',$date);
    if(!$slot || !$valid || $valid->format('Y-m-d')!==$date) return '<p>Choose a valid date and window.</p>';
    foreach(wc_get_products(['limit'=>-1,'status'=>'publish','meta_key'=>'_seer_fulfilment','meta_value'=>'scheduled_meal']) as $product){
        if($product->get_meta('_seer_fulfilment')!=='scheduled_meal') continue;
        $row=Seer_Kitchen::schedule($product->get_id(),(int)$slot['id'],$date);
        if(!$row) continue;
        $available=true; $message='View meal and choose delivery'; $price=$product->get_price_html();
        try { $ctx=Seer_Kitchen::context(['date'=>$date,'slot'=>$key]); $price=wc_price(Seer_Kitchen::quote($product->get_id(),1,$ctx)); }
        catch(InvalidArgumentException $e){$available=false; $message=$e->getMessage();}
        $html.='<a class="seer-meal" href="'.esc_url($product->get_permalink()).'">'.$product->get_image('medium').'<h3>'.esc_html($product->get_name()).'</h3><span>'.$price.'</span><p>'.esc_html($message).'</p></a>';
    }
    return $html.'</div></section>';
}
