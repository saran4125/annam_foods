<?php
defined('ABSPATH') || exit;

function seer_install_role(): void {
    $admin = get_role('administrator');
    if ($admin) {
        $caps = $admin->capabilities;
        foreach (['manage_network', 'manage_network_users', 'manage_network_plugins', 'manage_network_themes',
                  'install_plugins', 'update_plugins', 'delete_plugins', 'edit_plugins', 'install_themes',
                  'update_themes', 'delete_themes', 'edit_themes', 'edit_users', 'create_users', 'delete_users',
                  'promote_users', 'list_users', 'unfiltered_html'] as $cap) unset($caps[$cap]);
        $caps['manage_seer_kitchen'] = true;
        $caps['manage_woocommerce'] = true;
        $caps['edit_products'] = true;
        if (!get_role('store_owner')) add_role('store_owner', 'Store owner', $caps);
        else {
            $role = get_role('store_owner');
            foreach ($role->capabilities as $cap => $value) if (!isset($caps[$cap])) $role->remove_cap($cap);
            foreach ($caps as $cap => $value) $role->add_cap($cap, $value);
        }
    }
}
add_action('init', 'seer_install_role', 5);
add_filter('map_meta_cap', function ($caps, $cap, $user) {
    if (!is_super_admin($user) && in_array($cap, ['edit_user', 'delete_user', 'promote_user', 'create_users', 'list_users'], true)) return ['do_not_allow'];
    return $caps;
}, 10, 3);
add_action('admin_menu', function () {
    add_menu_page('Kitchen', 'Kitchen', 'manage_seer_kitchen', 'seer-kitchen', 'seer_admin_screen', 'dashicons-store', 30);
    foreach (['slots' => 'Delivery windows', 'schedules' => 'Meal schedules', 'zones' => 'Delivery zones', 'settings' => 'Kitchen settings'] as $key => $label) {
        add_submenu_page('seer-kitchen', $label, $label, 'manage_seer_kitchen', 'seer-' . $key, 'seer_admin_screen');
    }
});

function seer_admin_error(string $message): void {
    add_settings_error('seer', 'seer_error', $message, 'error');
}
function seer_admin_save(string $section): void {
    global $wpdb;
    if (!current_user_can('manage_seer_kitchen')) wp_die('Not allowed.', '', ['response' => 403]);
    check_admin_referer('seer_admin_' . $section);
    $raw = wp_unslash($_POST);
    try {
        if ($section==='schedules' && ($raw['seer_operation']??'')==='restore_weekly') {
            $id=absint($raw['record_id']??0);$table=$wpdb->prefix.'seer_schedules';
            $row=$wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE id=%d",$id),ARRAY_A);
            if(!$row || !preg_match('/^\d{4}-\d{2}-\d{2}$/D',$row['schedule_key']))throw new InvalidArgumentException('Choose a dated override from this store.');
            $wpdb->delete($table,['id'=>$id]);return;
        }
        if ($section === 'settings') {
            $days = filter_var($raw['booking_days'] ?? '', FILTER_VALIDATE_INT);
            if (!$days || $days < 1 || $days > 60) throw new InvalidArgumentException('Booking window must be 1–60 days.');
            $timezone = (string) ($raw['timezone'] ?? '');
            if (!in_array($timezone, DateTimeZone::listIdentifiers(), true)) throw new InvalidArgumentException('Choose a valid timezone.');
            update_option('seer_booking_days', $days);
            update_option('timezone_string', $timezone);
            update_option('seer_phone', sanitize_text_field($raw['phone'] ?? ''));
            update_option('seer_email', sanitize_email($raw['email'] ?? ''));
            update_option('seer_fssai', sanitize_text_field($raw['fssai'] ?? ''));
            update_option('seer_notice', sanitize_text_field($raw['notice'] ?? ''));
            return;
        }
        $id = absint($raw['record_id'] ?? 0);
        if ($section === 'slots') {
            foreach (['cutoff','delivery_from','delivery_to'] as $key) {
                if (!preg_match('/^([01]\d|2[0-3]):[0-5]\d$/D', $raw[$key] ?? '')) throw new InvalidArgumentException('Enter valid times.');
            }
            if (!$raw['label'] || !sanitize_title($raw['slot_key'])) throw new InvalidArgumentException('Enter a window name and key.');
            $row = ['slot_key' => sanitize_title($raw['slot_key']), 'label' => sanitize_text_field($raw['label']),
                'cutoff' => $raw['cutoff'], 'delivery_from' => $raw['delivery_from'], 'delivery_to' => $raw['delivery_to'],
                'active' => isset($raw['active']) ? 1 : 0, 'sort' => absint($raw['sort'] ?? 0)];
        } elseif ($section === 'zones') {
            $pin = preg_replace('/[\s-]/', '', $raw['pincode'] ?? '');
            if (!preg_match('/^[1-9]\d{5}$/D', $pin) || empty($raw['area'])) throw new InvalidArgumentException('Enter an area and valid pincode.');
            $slots = array_values(array_map('absint', $raw['slot_ids'] ?? []));
            $valid = array_column(seer_slots(), 'id');
            if (array_diff($slots, $valid)) throw new InvalidArgumentException('A window does not belong to this store.');
            $row = ['pincode' => $pin, 'area' => sanitize_text_field($raw['area']), 'fee' => Seer_Kitchen::money($raw['fee']),
                'minimum_order' => Seer_Kitchen::money($raw['minimum_order']), 'slot_ids' => wp_json_encode($slots), 'active' => isset($raw['active']) ? 1 : 0];
        } elseif ($section === 'schedules') {
            $product_id = absint($raw['product_id'] ?? 0);
            $product = wc_get_product($product_id);
            if (!$product || get_post_meta($product_id, '_seer_fulfilment', true) !== 'scheduled_meal') throw new InvalidArgumentException('Choose a meal from this store.');
            $slot_id = absint($raw['slot_id'] ?? 0);
            if (!in_array($slot_id, array_map('intval', array_column(seer_slots(), 'id')), true)) throw new InvalidArgumentException('Choose a window from this store.');
            $key = $raw['schedule_key'] ?? '';
            if (!preg_match('/^w:[1-7]$/D', $key)) {
                $date = DateTimeImmutable::createFromFormat('!Y-m-d', $key);
                if (!$date || $date->format('Y-m-d') !== $key) throw new InvalidArgumentException('Use an exact date or w:1 through w:7.');
            }
            $limit = $raw['quantity_limit'] ?? '';
            if ($limit !== '' && (!ctype_digit($limit) || (int) $limit > 100000)) throw new InvalidArgumentException('Enter a whole-number capacity or leave it blank.');
            $row = ['product_id' => $product_id, 'slot_id' => $slot_id, 'schedule_key' => $key,
                'available' => isset($raw['available']) ? 1 : 0, 'quantity_limit' => $limit === '' ? null : (int) $limit,
                'price_override' => $raw['price_override'] === '' ? null : Seer_Kitchen::money($raw['price_override'])];
        } else throw new InvalidArgumentException('Unknown screen.');
        $table = $wpdb->prefix . 'seer_' . $section;
        if ($id) {
            if (!$wpdb->get_var($wpdb->prepare("SELECT id FROM $table WHERE id=%d", $id))) throw new InvalidArgumentException('This record does not belong to this store.');
            $saved = $wpdb->update($table, $row, ['id' => $id]);
        } else $saved = $wpdb->insert($table, $row);
        if ($saved === false) throw new InvalidArgumentException('A record with this key already exists. Edit it instead.');
    } catch (InvalidArgumentException $e) { seer_admin_error($e->getMessage()); }
}

function seer_admin_input(string $key, string $label, array $row, string $type = 'text', string $default = ''): void {
    printf('<p><label>%s<br><input class="regular-text" type="%s" name="%s" value="%s" %s></label></p>', esc_html($label), esc_attr($type), esc_attr($key), esc_attr($row[$key] ?? $default), $type === 'number' ? 'min="0" step="1"' : '');
}
function seer_admin_screen(): void {
    global $wpdb;
    if (!current_user_can('manage_seer_kitchen')) wp_die('Not allowed.', '', ['response' => 403]);
    $section = str_replace('seer-', '', sanitize_key($_GET['page'] ?? 'kitchen'));
    echo '<div class="wrap"><h1>Kitchen · ' . esc_html(get_bloginfo('name')) . '</h1>';
    if ($section === 'kitchen') {
        echo '<p>Manage your website in <a href="' . esc_url(admin_url('site-editor.php')) . '">Appearance → Editor</a>. Manage your catalog in <a href="' . esc_url(admin_url('edit.php?post_type=product')) . '">Products</a>.</p>';
        echo '<p>Store preview: payments and order submission are disabled. Configure real delivery windows and zones before launch.</p></div>';
        return;
    }
    if (!in_array($section, ['slots','schedules','zones','settings'], true)) return;
    if ($_SERVER['REQUEST_METHOD'] === 'POST') seer_admin_save($section);
    settings_errors('seer');
    $row = [];
    if ($section !== 'settings') {
        $table = $wpdb->prefix . 'seer_' . $section;
        $rows = $wpdb->get_results("SELECT * FROM $table ORDER BY id", ARRAY_A);
        echo '<table class="widefat striped"><thead><tr><th>Record</th><th>Configuration</th><th></th></tr></thead><tbody>';
        foreach ($rows as $record) {
            printf('<tr><td>%s</td><td><code>%s</code></td><td><a href="%s">Edit</a></td></tr>', esc_html($record['label'] ?? $record['area'] ?? get_the_title($record['product_id'])), esc_html(wp_json_encode($record)), esc_url(add_query_arg(['page'=>'seer-'.$section,'edit'=>$record['id']], admin_url('admin.php'))));
            if($section==='schedules'&&!str_starts_with($record['schedule_key'],'w:')){
                echo '<tr><td colspan="3"><form method="post">';wp_nonce_field('seer_admin_schedules');
                printf('<input type="hidden" name="record_id" value="%d"><input type="hidden" name="seer_operation" value="restore_weekly"><button class="button">Restore weekly template for %s</button></form></td></tr>',$record['id'],esc_html($record['schedule_key']));
            }
        }
        echo '</tbody></table>';
        $edit = absint($_GET['edit'] ?? 0);
        if ($edit) $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE id=%d", $edit), ARRAY_A) ?: [];
    }
    echo '<h2>' . ($row ? 'Edit record' : ($section === 'settings' ? 'Store settings' : 'Add record')) . '</h2><form method="post">';
    wp_nonce_field('seer_admin_' . $section);
    printf('<input type="hidden" name="record_id" value="%d">', $row['id'] ?? 0);
    if ($section === 'slots') {
        foreach (['label'=>'Name','slot_key'=>'Key (for example lunch)','cutoff'=>'Order cutoff','delivery_from'=>'Delivery from','delivery_to'=>'Delivery to','sort'=>'Sort order'] as $key=>$label) seer_admin_input($key,$label,$row,in_array($key,['cutoff','delivery_from','delivery_to'],true)?'time':($key==='sort'?'number':'text'));
    } elseif ($section === 'zones') {
        foreach (['pincode'=>'Pincode','area'=>'Area','fee'=>'Delivery fee (₹)','minimum_order'=>'Minimum order (₹)'] as $key=>$label) seer_admin_input($key,$label,$row,'text',in_array($key,['fee','minimum_order'],true)?'0':'');
        $selected = json_decode($row['slot_ids'] ?? '[]', true) ?: [];
        echo '<p>Allowed windows (none selected = all)</p>';
        foreach (seer_slots() as $slot) printf('<label><input type="checkbox" name="slot_ids[]" value="%d" %s>%s</label> ', $slot['id'], checked(in_array((int)$slot['id'],$selected,true),true,false),esc_html($slot['label']));
    } elseif ($section === 'schedules') {
        echo '<p>A dated row overrides the weekly row. Disable a dated row to remove a dish just for that date. Delete a dated row in the list below to restore the weekly template.</p><label>Meal <select name="product_id">';
        foreach (wc_get_products(['limit'=>-1,'status'=>['publish','draft']]) as $product) {
            if ($product->get_meta('_seer_fulfilment') !== 'scheduled_meal') continue;
            printf('<option value="%d" %s>%s</option>',$product->get_id(),selected($row['product_id']??0,$product->get_id(),false),esc_html($product->get_name()));
        }
        echo '</select></label><p><label>Window <select name="slot_id">';
        foreach(seer_slots() as $slot) printf('<option value="%d" %s>%s</option>',$slot['id'],selected($row['slot_id']??0,$slot['id'],false),esc_html($slot['label']));
        echo '</select></label></p>';
        seer_admin_input('schedule_key','Date YYYY-MM-DD, or weekday w:1 (Monday) through w:7 (Sunday)',$row);
        seer_admin_input('quantity_limit','Capacity (blank = unlimited)',$row,'number');
        seer_admin_input('price_override','Price override (blank = catalog price)',$row);
        printf('<p><label><input type="checkbox" name="available" %s>Available</label></p>',checked($row['available']??1,1,false));
    } else {
        foreach (['booking_days'=>'Booking window (days)','timezone'=>'Timezone','phone'=>'Support phone','email'=>'Support email','fssai'=>'FSSAI number','notice'=>'Announcement'] as $key=>$label) {
            $option = $key === 'timezone' ? 'timezone_string' : 'seer_'.$key;
            $value = get_option($option,$key==='timezone'?'Asia/Kolkata':($key==='booking_days'?'2':''));
            seer_admin_input($key,$label,[$key=>$value],$key==='booking_days'?'number':'text');
        }
    }
    if(in_array($section,['slots','zones'],true)) printf('<p><label><input type="checkbox" name="active" %s>Active</label></p>',checked($row['active']??1,1,false));
    submit_button('Save');
    echo '</form></div>';
}
