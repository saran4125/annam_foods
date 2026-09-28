<?php
defined('ABSPATH') || exit;

final class Seer_Kitchen {
    public static function money($value): string {
        $value = (string) $value;
        if (!preg_match('/^\d{1,10}(?:\.\d{1,2})?$/D', $value)) {
            throw new InvalidArgumentException('Enter a non-negative amount with at most two decimal places.');
        }
        return bcadd($value, '0', 2);
    }

    public static function date(string $value, ?DateTimeImmutable $now = null): DateTimeImmutable {
        $now ??= new DateTimeImmutable('now', wp_timezone());
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value, wp_timezone());
        if (!$date || $date->format('Y-m-d') !== $value) throw new InvalidArgumentException('Choose a valid delivery date.');
        $today = $now->setTime(0, 0);
        $horizon = max(1, min(60, (int) get_option('seer_booking_days', 2)));
        if ($date < $today || $date >= $today->modify("+$horizon days")) {
            throw new InvalidArgumentException('Choose a date in this store’s booking window.');
        }
        return $date;
    }

    public static function context(array $raw, ?DateTimeImmutable $now = null): array {
        global $wpdb;
        $now ??= new DateTimeImmutable('now', wp_timezone());
        $date = self::date((string) ($raw['date'] ?? ''), $now);
        $key = (string) ($raw['slot'] ?? '');
        $slot = $wpdb->get_row($wpdb->prepare(
            "SELECT * FROM {$wpdb->prefix}seer_slots WHERE slot_key=%s AND active=1", $key
        ), ARRAY_A);
        if (!$slot) throw new InvalidArgumentException('Choose a delivery window configured by this store.');
        $cutoff = new DateTimeImmutable($date->format('Y-m-d') . ' ' . $slot['cutoff'], wp_timezone());
        if ($now >= $cutoff) throw new InvalidArgumentException('Ordering has closed for this delivery window.');
        return ['date' => $date->format('Y-m-d'), 'slot' => $key, 'slot_id' => (int) $slot['id']];
    }

    public static function schedule(int $product, int $slot, string $date): ?array {
        global $wpdb;
        $weekday = 'w:' . (new DateTimeImmutable($date, wp_timezone()))->format('N');
        // ISO weekday: Monday=1. Exact date wins even when it disables a meal.
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT * FROM {$wpdb->prefix}seer_schedules WHERE product_id=%d AND slot_id=%d AND schedule_key IN (%s,%s)",
            $product, $slot, $date, $weekday
        ), ARRAY_A);
        foreach ($rows as $row) if ($row['schedule_key'] === $date) return $row;
        return $rows[0] ?? null;
    }

    public static function quote(int $product_id, int $quantity, array $context): string {
        if ($quantity < 1 || $quantity > 99) throw new InvalidArgumentException('Quantity must be between 1 and 99.');
        $product = wc_get_product($product_id);
        if (!$product || $product->get_status() !== 'publish' || !$product->is_in_stock()) {
            throw new InvalidArgumentException('This product is not available.');
        }
        if (!$product->has_enough_stock($quantity)) throw new InvalidArgumentException('This quantity is not available.');
        $parent = $product->get_parent_id() ?: $product_id;
        $price = $product->get_price('edit');
        if (get_post_meta($parent, '_seer_fulfilment', true) === 'scheduled_meal') {
            if (!$context) throw new InvalidArgumentException('Choose a date and meal window before adding this meal.');
            $row = self::schedule($parent, $context['slot_id'], $context['date']);
            if (!$row || !$row['available']) throw new InvalidArgumentException('This meal is not on the selected menu.');
            if ($row['quantity_limit'] !== null && $quantity + (int) $row['quantity_sold'] > (int) $row['quantity_limit']) {
                throw new InvalidArgumentException('This meal quantity is sold out.');
            }
            if ($row['price_override'] !== null) $price = $row['price_override'];
        }
        return self::money($price);
    }

    public static function zone(string $pincode, int $zone_id = 0, int $slot_id = 0): array {
        global $wpdb;
        $pincode = preg_replace('/[\s-]/', '', $pincode);
        if (!preg_match('/^[1-9]\d{5}$/D', $pincode)) throw new InvalidArgumentException('Enter a six-digit Indian pincode.');
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT * FROM {$wpdb->prefix}seer_zones WHERE pincode=%s AND active=1 ORDER BY id", $pincode
        ), ARRAY_A);
        $rows = array_values(array_filter($rows, function ($row) use ($slot_id, $zone_id) {
            $slots = json_decode($row['slot_ids'], true) ?: [];
            return (!$zone_id || (int) $row['id'] === $zone_id) && (!$slot_id || !$slots || in_array($slot_id, $slots, true));
        }));
        if (!$rows) throw new InvalidArgumentException('This store has no delivery zone configured for that pincode and window.');
        return $rows;
    }

    public static function persist_context(array $raw): array {
        $context = self::context($raw);
        $old = WC()->session->get('seer_context', []);
        if (!WC()->cart->is_empty() && $old && ($old['date'] !== $context['date'] || $old['slot'] !== $context['slot'])) {
            throw new InvalidArgumentException('Your cart uses another delivery date or window. Empty it before changing delivery.');
        }
        WC()->session->set('seer_context', $context);
        // A zone selected for a previous delivery window must not survive it.
        if ($old !== $context) WC()->session->__unset('seer_zone');
        return $context;
    }
}
