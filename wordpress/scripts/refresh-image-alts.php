<?php
/** Replace untouched source filenames with readable product names. */
if (!defined('WP_CLI') || !WP_CLI || get_current_blog_id() === get_main_site_id()) {
    throw new RuntimeException('Run for a kitchen with WP-CLI --url.');
}
$updated = 0;
$ids = get_posts(['post_type' => 'product', 'post_status' => 'any', 'fields' => 'ids', 'posts_per_page' => -1]);
foreach ($ids as $id) {
    $product = wc_get_product($id);
    if (!$product || !$product->get_meta('_seer_source_url')) continue;
    foreach (array_merge([$product->get_image_id()], $product->get_gallery_image_ids()) as $media_id) {
        if (!$media_id) continue;
        $source = get_post_meta($media_id, '_seer_source_url', true);
        if (!$source) continue;
        $current = get_post_meta($media_id, '_wp_attachment_image_alt', true);
        $filename = sanitize_text_field(pathinfo(basename(parse_url($source, PHP_URL_PATH)), PATHINFO_FILENAME));
        if ($current && $current !== $filename) continue; // preserve owner edits
        update_post_meta($media_id, '_wp_attachment_image_alt', sanitize_text_field($product->get_name()));
        $updated++;
    }
}
$terms = get_terms(['taxonomy' => 'product_cat', 'hide_empty' => false]);
if (!is_wp_error($terms)) foreach ($terms as $term) {
    $media_id = (int) get_term_meta($term->term_id, 'thumbnail_id', true);
    if (!$media_id) continue;
    $source = get_post_meta($media_id, '_seer_source_url', true);
    if (!$source) continue;
    $current = get_post_meta($media_id, '_wp_attachment_image_alt', true);
    $filename = sanitize_text_field(pathinfo(basename(parse_url($source, PHP_URL_PATH)), PATHINFO_FILENAME));
    if ($current && $current !== $filename) continue;
    update_post_meta($media_id, '_wp_attachment_image_alt', sanitize_text_field($term->name));
    $updated++;
}
$logo_id = (int) get_theme_mod('custom_logo');
if ($logo_id) {
    $current = get_post_meta($logo_id, '_wp_attachment_image_alt', true);
    $source = get_post_meta($logo_id, '_seer_source_url', true);
    $filename = $source ? sanitize_text_field(pathinfo(basename(parse_url($source, PHP_URL_PATH)), PATHINFO_FILENAME)) : '';
    if (!$current || ($filename && $current === $filename)) {
        update_post_meta($logo_id, '_wp_attachment_image_alt', get_bloginfo('name').' logo');
        $updated++;
    }
}
WP_CLI::success('Updated '.$updated.' untouched image descriptions.');
