<?php
declare(strict_types=1);
namespace Annam;

final class Cart {
    public static function add(Store $store, array $input): void {
        $id = filter_var($input['item_id'] ?? '', FILTER_VALIDATE_INT);
        $quantity = filter_var($input['quantity'] ?? '1', FILTER_VALIDATE_INT);
        if (!$id || !$quantity || $quantity < 1 || $quantity > 99) throw new HttpError(422, 'Choose a quantity between 1 and 99.');
        $item = $store->item($id);
        if (!$item['active']) throw new HttpError(422, 'This item is unavailable.');
        $kind = $item['fulfilment'];
        if(!($store->config['features']['website_ordering']??true))throw new HttpError(422,'Website ordering is closed.');
        if($kind==='courier'&&!($store->config['features']['snacks_courier']??false))throw new HttpError(422,'Shop ordering is closed.');
        $date = $kind === 'scheduled' ? Store::date($input['date'] ?? '') : null;
        $slotId = $kind === 'scheduled' ? (int)($input['slot_id'] ?? 0) : null;
        if ($kind === 'scheduled') self::scheduledItem($store, $id, $date, $slotId, $quantity);
        $cart = $_SESSION['cart'] ?? ['kind' => $kind, 'date' => $date, 'slot_id' => $slotId, 'lines' => []];
        if ($cart['kind'] !== $kind || $cart['date'] !== $date || $cart['slot_id'] !== $slotId) throw new HttpError(422, 'Meals, different meal times and shop items require separate carts. Clear the cart first.');
        $newQuantity = ($cart['lines'][$id] ?? 0) + $quantity;
        if ($newQuantity > 99) throw new HttpError(422, 'Maximum quantity is 99 per item.');
        if ($kind === 'scheduled') self::scheduledItem($store, $id, $date, $slotId, $newQuantity);
        $cart['lines'][$id] = $newQuantity;
        $_SESSION['cart'] = $cart;
    }
    public static function set(Store $store,int $id,int $quantity): void {
        $cart=$_SESSION['cart']??['lines'=>[]];if(!isset($cart['lines'][$id]))throw new HttpError(404,'Cart item not found.');if($quantity<0||$quantity>99)throw new HttpError(422,'Choose a quantity from 0 to 99.');if($quantity===0)unset($cart['lines'][$id]);else $cart['lines'][$id]=$quantity;self::quote($store,$cart);$_SESSION['cart']=$cart;
    }
    private static function scheduledItem(Store $store, int $id, string $date, int $slotId, int $quantity): array {
        $slot = $store->slot($slotId);
        if (!$slot['active'] || $date < date('Y-m-d') || ($date === date('Y-m-d') && date('H:i:s') >= $slot['order_cutoff'])) throw new HttpError(422, 'Ordering has closed for this meal.');
        if (in_array($date, $store->config['checkout_settings']['closed_dates'] ?? [], true)) throw new HttpError(422, 'The kitchen is closed on this date.');
        foreach ($store->menu($date, $slotId) as $entry) {
            if ((int)$entry['id'] === $id) {
                if ($entry['qty_limit'] !== null && $quantity > $entry['qty_limit'] - $entry['qty_sold']) throw new HttpError(422, 'Not enough portions are available.');
                return $entry;
            }
        }
        throw new HttpError(422, 'This dish is not available for the selected meal and date.');
    }
    public static function quote(Store $store, ?array $cart = null): array {
        $cart ??= $_SESSION['cart'] ?? ['lines' => []];
        $lines = []; $subtotal = 0;
        foreach ($cart['lines'] as $id => $quantity) {
            if (!is_int($quantity) || $quantity < 1 || $quantity > 99) throw new HttpError(422, 'Invalid cart quantity.');
            $item = $store->item((int)$id);
            if (!$item['active'] || $item['fulfilment'] !== $cart['kind']) throw new HttpError(422, 'A cart item is no longer available. Remove it before proceeding.');
            $price = $item['price'];
            if ($cart['kind'] === 'scheduled') $price = self::scheduledItem($store, (int)$id, $cart['date'], $cart['slot_id'], $quantity)['effective_price'];
            $unit = Money::parse($price); $amount = $unit * $quantity;
            $lines[] = ['item' => $item, 'quantity' => $quantity, 'unit' => $unit, 'amount' => $amount];
            $subtotal += $amount;
        }
        return ['lines' => $lines, 'subtotal' => $subtotal, 'cart' => $cart];
    }
}
