<?php
defined('ABSPATH') || exit;

function seer_install_schema(): void {
    global $wpdb;
    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    $charset = $wpdb->get_charset_collate();
    // Never base_prefix: every kitchen gets independent tables.
    $prefix = $wpdb->prefix . 'seer_';
    dbDelta("CREATE TABLE {$prefix}slots (
        id bigint unsigned NOT NULL AUTO_INCREMENT,
        slot_key varchar(40) NOT NULL,
        label varchar(100) NOT NULL,
        cutoff time NOT NULL,
        delivery_from time NOT NULL,
        delivery_to time NOT NULL,
        active tinyint NOT NULL DEFAULT 1,
        sort int NOT NULL DEFAULT 0,
        PRIMARY KEY (id),
        UNIQUE KEY slot_key (slot_key)
    ) $charset;");
    dbDelta("CREATE TABLE {$prefix}schedules (
        id bigint unsigned NOT NULL AUTO_INCREMENT,
        product_id bigint unsigned NOT NULL,
        slot_id bigint unsigned NOT NULL,
        schedule_key varchar(10) NOT NULL,
        available tinyint NOT NULL DEFAULT 1,
        quantity_limit int unsigned DEFAULT NULL,
        quantity_sold int unsigned NOT NULL DEFAULT 0,
        price_override decimal(12,2) DEFAULT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY product_slot_day (product_id,slot_id,schedule_key)
    ) $charset;");
    dbDelta("CREATE TABLE {$prefix}zones (
        id bigint unsigned NOT NULL AUTO_INCREMENT,
        pincode varchar(6) NOT NULL,
        area varchar(100) NOT NULL,
        fee decimal(12,2) NOT NULL DEFAULT 0,
        minimum_order decimal(12,2) NOT NULL DEFAULT 0,
        slot_ids text NOT NULL,
        active tinyint NOT NULL DEFAULT 1,
        PRIMARY KEY (id),
        UNIQUE KEY pincode_area (pincode,area)
    ) $charset;");
    update_option('seer_schema_version', '1');
}
add_action('init', function () {
    if (get_option('seer_schema_version') !== '1') seer_install_schema();
}, 1);

function seer_slots(): array {
    global $wpdb;
    return $wpdb->get_results("SELECT * FROM {$wpdb->prefix}seer_slots WHERE active=1 ORDER BY sort,id", ARRAY_A);
}
