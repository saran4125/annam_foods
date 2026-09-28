<?php
if (!defined('WP_CLI') || !WP_CLI || html_entity_decode(get_option('blogname'), ENT_QUOTES, 'UTF-8') !== 'Leaf & Ladle · Demo') throw new RuntimeException('Demo site only.');
seer_install_schema();
global $wpdb;
if(!get_option('seer_demo_seeded')){
    $product=new WC_Product_Simple();$product->set_name('Demo vegetable lunch');$product->set_slug('demo-vegetable-lunch');$product->set_regular_price('120.00');$product->set_status('publish');$product->set_description('Demonstration fixture — not an Annam product.');$product->update_meta_data('_seer_fulfilment','scheduled_meal');$product->save();
    $goods=new WC_Product_Simple();$goods->set_name('Demo pantry snack');$goods->set_slug('demo-pantry-snack');$goods->set_regular_price('80.00');$goods->set_status('publish');$goods->set_featured(true);$goods->update_meta_data('_seer_fulfilment','packaged_goods');$goods->save();
    $wpdb->insert($wpdb->prefix.'seer_slots',['slot_key'=>'lunch','label'=>'Demo lunch','cutoff'=>'23:59:00','delivery_from'=>'12:30:00','delivery_to'=>'14:00:00']);
    $slot=(int)$wpdb->insert_id;
    for($day=1;$day<=7;$day++)$wpdb->insert($wpdb->prefix.'seer_schedules',['product_id'=>$product->get_id(),'slot_id'=>$slot,'schedule_key'=>'w:'.$day,'available'=>1,'quantity_limit'=>20,'quantity_sold'=>0]);
    $wpdb->insert($wpdb->prefix.'seer_zones',['pincode'=>'600005','area'=>'Demo zone — test data','fee'=>'20.00','minimum_order'=>'150.00','slot_ids'=>'[]']);
    update_option('seer_notice','DEMONSTRATION STORE · Test products and delivery rules');
    $styles=WP_Theme_JSON_Resolver::get_user_data();
    $global=get_posts(['post_type'=>'wp_global_styles','posts_per_page'=>1,'post_status'=>'publish']);
    $data=['version'=>3,'isGlobalStylesUserThemeJSON'=>true,'settings'=>['color'=>['palette'=>['theme'=>[
        ['slug'=>'brand','name'=>'Brand','color'=>'#95b57d'],['slug'=>'dark','name'=>'Dark','color'=>'#203828'],['slug'=>'cream','name'=>'Cream','color'=>'#f7faf3'],['slug'=>'white','name'=>'White','color'=>'#ffffff'],['slug'=>'muted','name'=>'Muted','color'=>'#637663']
    ]]]]];
    $post=['post_type'=>'wp_global_styles','post_status'=>'publish','post_title'=>'Demo styles','post_name'=>'wp-global-styles-seerkitchen','post_content'=>wp_json_encode($data),'tax_input'=>['wp_theme'=>['seerkitchen']]];
    if($global)$post['ID']=$global[0]->ID;
    wp_insert_post($post);
    update_option('seer_demo_seeded',1);
}
flush_rewrite_rules();
WP_CLI::success('Demo fixtures are ready; Annam has no seeded delivery zones.');
