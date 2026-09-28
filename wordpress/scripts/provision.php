<?php
/** Run as the platform operator with wp eval-file. Never through a tenant route. */
if (!defined('WP_CLI') || !WP_CLI || !is_multisite()) throw new RuntimeException('Platform CLI only.');
require_once ABSPATH . 'wp-admin/includes/plugin.php';

if(!defined('SEER_PROVISION_LIBRARY')){
update_network_option(get_current_network_id(),'registration','none');
update_network_option(get_current_network_id(),'menu_items',['plugins'=>1]);
WP_Theme::network_enable_theme('seerkitchen');
$annam=seer_provision_site('annam.localhost:8090','Annam Foods','annam-owner',getenv('ANNAM_OWNER_PASSWORD'));
$demo=seer_provision_site('demo.localhost:8090','Leaf & Ladle · Demo','demo-owner',getenv('DEMO_OWNER_PASSWORD'));
WP_CLI::success('Provisioned Annam and Leaf & Ladle with independent owner accounts.');
}
