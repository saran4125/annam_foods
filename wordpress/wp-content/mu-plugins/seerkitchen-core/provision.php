<?php
defined('ABSPATH') || exit;
function seer_page(string $slug, string $title, string $content, string $status = 'publish'): int {
    $page = get_page_by_path($slug, OBJECT, 'page');
    if ($page) return $page->ID; // provisioning never overwrites owner content
    return wp_insert_post(['post_type'=>'page','post_status'=>$status,'post_name'=>$slug,'post_title'=>$title,'post_content'=>$content]);
}
function seer_home_blocks(array $hero = [], array $promos = [], string $story_image = ''): string {
    $block = fn($name,$attrs) => '<!-- wp:'.$name.' '.wp_json_encode((object)$attrs).' /-->';
    $html=$block('seerkitchen/hero',['items'=>$hero,'align'=>'full']);
    $html.=$block('seerkitchen/promotions',['items'=>$promos]);
    $html.='<!-- wp:heading {"textAlign":"center","className":"seer-section-title"} --><h2 class="wp-block-heading has-text-align-center seer-section-title">A little taste of home</h2><!-- /wp:heading -->';
    $html.='<!-- wp:paragraph {"align":"center","className":"seer-section-subtitle"} --><p class="has-text-align-center seer-section-subtitle">Discover our sweets, snacks and pantry favourites.</p><!-- /wp:paragraph -->';
    $html.='<!-- wp:woocommerce/product-collection {"queryId":1,"query":{"perPage":6,"pages":1,"offset":0,"postType":"product","order":"asc","orderBy":"menu_order","inherit":false,"isProductCollectionBlock":true,"featured":true},"displayLayout":{"type":"flex","columns":6},"align":"wide"} -->';
    $html.='<!-- wp:woocommerce/product-template --><!-- wp:woocommerce/product-image {"imageSizing":"thumbnail","isDescendentOfQueryLoop":true} /--><!-- wp:post-title {"level":3,"isLink":true,"fontSize":"medium"} /--><!-- wp:woocommerce/product-price {"isDescendentOfQueryLoop":true} /--><!-- wp:woocommerce/product-button {"isDescendentOfQueryLoop":true} /--><!-- /wp:woocommerce/product-template --><!-- /wp:woocommerce/product-collection -->';
    $html.='<!-- wp:buttons {"layout":{"type":"flex","justifyContent":"center"}} --><div class="wp-block-buttons"><!-- wp:button {"backgroundColor":"dark","textColor":"cream"} --><div class="wp-block-button"><a class="wp-block-button__link has-cream-color has-dark-background-color has-text-color has-background wp-element-button" href="'.esc_url(home_url('/shop/')).'">Explore the store →</a></div><!-- /wp:button --></div><!-- /wp:buttons -->';
    $html.=$block('seerkitchen/categories',['title'=>'Shop your favourites']);
    $html.=$block('seerkitchen/daily-menu',[]);
    $html.='<!-- wp:columns {"className":"seer-story","verticalAlignment":"center"} --><div class="wp-block-columns are-vertically-aligned-center seer-story"><!-- wp:column {"verticalAlignment":"center"} --><div class="wp-block-column is-vertically-aligned-center">';
    if($story_image) $html.='<!-- wp:image {"sizeSlug":"large"} --><figure class="wp-block-image size-large"><img src="'.esc_url($story_image).'" alt="Food from our kitchen"/></figure><!-- /wp:image -->';
    $html.='</div><!-- /wp:column --><!-- wp:column {"verticalAlignment":"center"} --><div class="wp-block-column is-vertically-aligned-center"><!-- wp:paragraph --><p>FROM OUR KITCHEN TO YOUR HOME</p><!-- /wp:paragraph --><!-- wp:heading --><h2 class="wp-block-heading">Good food.<br>A familiar feeling.</h2><!-- /wp:heading --><!-- wp:paragraph --><p>Explore the flavours you love, choose your favourites, and make room for a little everyday goodness.</p><!-- /wp:paragraph --></div><!-- /wp:column --></div><!-- /wp:columns -->';
    return $html;
}
function seer_provision_site(string $domain,string $name,string $owner,string $password): int {
    $site=get_sites(['domain'=>$domain,'path'=>'/','number'=>1]);
    $platform=get_user_by('login',get_super_admins()[0]);
    $id=$site?(int)$site[0]->blog_id:wpmu_create_blog($domain,'/',$name,$platform->ID,[],get_current_network_id());
    if(is_wp_error($id)) throw new RuntimeException($id->get_error_message());
    switch_to_blog($id);
    if (!get_option('woocommerce_db_version')) WC_Install::install();
    seer_install_schema();
    seer_install_role();
    $user=get_user_by('login',$owner);
    if(!$user){
        $uid=wp_insert_user(['user_login'=>$owner,'user_pass'=>$password,'user_email'=>$owner.'@example.test','display_name'=>$name.' owner']);
        if(is_wp_error($uid)) throw new RuntimeException($uid->get_error_message());
    }else $uid=$user->ID;
    add_user_to_blog($id,$uid,'store_owner');
    if(!get_option('seer_provisioned')){
        update_option('blogname',$name);
        update_option('blogdescription','Food made with care. A little taste of home.');
        update_option('timezone_string','Asia/Kolkata');
        update_option('seer_booking_days',2);
        update_option('woocommerce_currency','INR');
        update_option('woocommerce_default_country','IN:TN');
        update_option('woocommerce_price_num_decimals',2);
        update_option('woocommerce_enable_reviews','yes');
        update_option('woocommerce_tax_based_on','shipping');
        update_option('woocommerce_calc_taxes','no');
        update_option('woocommerce_onboarding_profile',['completed'=>true]);
        update_option('woocommerce_allow_tracking','no');
        update_option('woocommerce_permalinks',['product_base'=>'/products','category_base'=>'categories','tag_base'=>'product-tag','attribute_base'=>'']);
        update_option('permalink_structure','/%postname%/');
        switch_theme('seerkitchen');
        $home=seer_page('home','Home',seer_home_blocks());
        $shop=seer_page('shop','Our store','');
        $cart=seer_page('cart','Your cart','<!-- wp:shortcode -->[woocommerce_cart]<!-- /wp:shortcode -->');
        $checkout=seer_page('checkout','Checkout','<!-- wp:paragraph --><p>Checkout opens after setup.</p><!-- /wp:paragraph -->');
        seer_page('daily-menu','Daily meals','<!-- wp:seerkitchen/daily-menu /--><!-- wp:seerkitchen/delivery /-->');
        update_option('show_on_front','page');update_option('page_on_front',$home);
        update_option('woocommerce_shop_page_id',$shop);update_option('woocommerce_cart_page_id',$cart);update_option('woocommerce_checkout_page_id',$checkout);
        $nav='';
        foreach(['Home'=>'/','Shop favourites'=>'/shop/','Daily meals'=>'/daily-menu/'] as $label=>$path) $nav.='<!-- wp:navigation-link '.wp_json_encode(['label'=>$label,'url'=>home_url($path),'kind'=>'custom','isTopLevelLink'=>true]).' /-->';
        wp_insert_post(['post_type'=>'wp_navigation','post_title'=>'Store navigation','post_status'=>'publish','post_content'=>$nav]);
        update_option('seer_provisioned',1);
        // WP rewrite hooks were registered before switch_to_blog; explicit structure
        // generation keeps mapped sites consistent on the first provisioning run.
        WC_Post_Types::register_taxonomies();WC_Post_Types::register_post_types();
        flush_rewrite_rules();
    }
    restore_current_blog();
    return (int)$id;
}
if(defined('WP_CLI')&&WP_CLI)WP_CLI::add_command('seer provision',function($args,$assoc){
    foreach(['domain','name','owner','email']as$key)if(empty($assoc[$key]))WP_CLI::error('Missing --'.$key.'.');
    $domain=strtolower($assoc['domain']);
    if(!preg_match('/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9-]+(?::\d{2,5})?$/D',$domain)||!is_email($assoc['email']))WP_CLI::error('Use a valid domain and owner email.');
    $owner=sanitize_user($assoc['owner'],true);if(!$owner)WP_CLI::error('Invalid owner login.');
    $existing=get_sites(['domain'=>$domain,'path'=>'/','number'=>1]);$user=get_user_by('login',$owner);
    if($user&&(!$existing||!is_user_member_of_blog($user->ID,$existing[0]->blog_id)))WP_CLI::error('Choose a unique owner account for this kitchen.');
    if($existing){WP_CLI::success('Site already exists; owner content and password preserved.');return;}
    $password=wp_generate_password(28,true,true);$id=seer_provision_site($domain,$assoc['name'],$owner,$password);
    wp_update_user(['ID'=>get_user_by('login',$owner)->ID,'user_email'=>$assoc['email']]);
    $path='/opt/seer/reports/onboarding-'.$id.'-credentials.json';
    file_put_contents($path,wp_json_encode(['site_id'=>$id,'domain'=>$domain,'owner'=>$owner,'password'=>$password],JSON_PRETTY_PRINT));chmod($path,0600);
    WP_CLI::success('Site created. Credentials: '.$path.'. Add the registered host to Caddy and SEER_ALLOWED_HOSTS, then reload the services.');
});
