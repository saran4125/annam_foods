<?php
defined('ABSPATH') || exit;
add_action('after_setup_theme', function () {
    add_theme_support('woocommerce');
    add_theme_support('wc-product-gallery-zoom');
    add_theme_support('wc-product-gallery-lightbox');
    add_theme_support('wc-product-gallery-slider');
    add_editor_style('assets/store.css');
});
add_action('wp_enqueue_scripts', function () {
    wp_enqueue_style('seer-store', get_theme_file_uri('assets/store.css'), [], filemtime(get_theme_file_path('assets/store.css')));
    wp_enqueue_script('seer-store', get_theme_file_uri('assets/store.js'), [], '1.0', true);
});
add_filter('woocommerce_product_review_count', fn($count) => $count);
add_action('pre_get_posts', function ($query) {
    if (!is_admin() && $query->is_main_query() && $query->is_search()) {
        $query->set('post_type', 'product');
    }
});
add_filter('woocommerce_product_tabs', function ($tabs) {
    global $product;
    if ($product && !$product->get_review_count()) unset($tabs['reviews']);
    return $tabs;
});
