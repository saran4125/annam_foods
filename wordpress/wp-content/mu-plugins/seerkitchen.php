<?php
/**
 * Plugin Name: SeerKitchen Core
 * Description: Site-scoped kitchen rules, owner tools, commerce validation and preview safety.
 * Version: 1.0.0
 * Requires PHP: 8.3
 */
defined('ABSPATH') || exit;
define('SEER_CORE_DIR', __DIR__ . '/seerkitchen-core');
foreach (['schema', 'services', 'commerce', 'admin', 'blocks', 'import', 'provision'] as $module) {
    require_once SEER_CORE_DIR . '/' . $module . '.php';
}

// Caddy is the first boundary; PHP fails closed too, including direct FastCGI.
add_action('muplugins_loaded', function () {
    if (defined('WP_CLI') && WP_CLI) return;
    $host = strtolower(explode(':', $_SERVER['HTTP_HOST'] ?? '')[0]);
    $allowed = defined('SEER_ALLOWED_HOSTS') ? SEER_ALLOWED_HOSTS : [];
    if (!$host || !in_array($host, $allowed, true)) {
        status_header(404);
        exit('No store is configured for this address.');
    }
});

// Multisite accounts are shared identities, but all authority is site-local.
add_action('admin_init', function () {
    if (!is_super_admin() && is_user_logged_in() && !is_user_member_of_blog()) {
        wp_die('You do not have access to this store.', 'Store access', ['response' => 403]);
    }
});
add_filter('rest_authentication_errors', function ($result) {
    if ($result) return $result;
    if (is_user_logged_in() && !is_super_admin() && !is_user_member_of_blog()) {
        return new WP_Error('seer_wrong_store', 'You do not have access to this store.', ['status' => 403]);
    }
    return $result;
});
add_filter('allow_subdirectory_install', '__return_true');
add_filter('wpmu_signup_location', fn() => home_url('/'));

function seer_preview_enabled(): bool {
    // This release has no supported live-order mode, even if an option changes.
    return true;
}
