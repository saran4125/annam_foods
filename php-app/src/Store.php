<?php
declare(strict_types=1);
namespace Annam;

final class Store {
    public readonly array $tenant;
    public array $config;
    public function __construct(public readonly Database $db) {
        $slug = getenv('STORE_SLUG') ?: 'annam';
        $this->tenant = $db->one('SELECT * FROM tenancy_tenant WHERE slug=? AND status=?', [$slug, 'active'])
            ?? throw new HttpError(404, 'Store not found.');
        $this->config = $db->one('SELECT * FROM tenancy_tenantconfig WHERE tenant_id=?', [$this->id()])
            ?? throw new \RuntimeException('Store settings are missing.');
        foreach (['theme', 'features', 'home_sections', 'storefront_design', 'checkout_settings'] as $field) {
            $this->config[$field] = json_decode($this->config[$field] ?? '{}', true, 512, JSON_THROW_ON_ERROR);
        }
    }
    public function id(): int { return (int)$this->tenant['id']; }
    public function name(): string { return $this->config['brand_name'] ?: $this->tenant['name']; }
    public function slots(): array { return $this->db->rows('SELECT * FROM catalog_slot WHERE tenant_id=? AND active ORDER BY sort,key', [$this->id()]); }
    public function slot(int $id): array { return $this->db->one('SELECT * FROM catalog_slot WHERE tenant_id=? AND id=?', [$this->id(), $id]) ?? throw new HttpError(404, 'Meal not found.'); }
    public function items(string $kind = '', string $query = '', ?int $category = null): array {
        $sql = 'SELECT i.*,c.name AS category_name FROM catalog_menuitem i LEFT JOIN catalog_menucategory c ON c.id=i.category_id AND c.tenant_id=i.tenant_id WHERE i.tenant_id=?';
        $params = [$this->id()];
        if ($kind) { $sql .= ' AND i.fulfilment=?'; $params[] = $kind; }
        if ($query) { $sql .= ' AND i.name ILIKE ?'; $params[] = '%' . $query . '%'; }
        if ($category) { $sql .= ' AND i.category_id=?'; $params[] = $category; }
        return $this->db->rows($sql . ' ORDER BY i.sort,i.name', $params);
    }
    public function item(int $id): array {
        return $this->db->one('SELECT * FROM catalog_menuitem WHERE tenant_id=? AND id=?', [$this->id(), $id]) ?? throw new HttpError(404, 'Dish not found.');
    }
    public function categories(): array { return $this->db->rows('SELECT * FROM catalog_menucategory WHERE tenant_id=? ORDER BY sort,name', [$this->id()]); }
    public function pages(): array { return $this->db->rows('SELECT * FROM content_page WHERE tenant_id=? AND published ORDER BY sort,title', [$this->id()]); }
    public function logo(): string { return image_url($this->config['theme']['logo_url'] ?? '') ?: '/media/brand/annam-logo.png'; }
    public static function date(string $value): string {
        $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        if (!$date || $date->format('Y-m-d') !== $value) throw new HttpError(422, 'Choose a valid menu date.');
        return $value;
    }
    public function menu(string $date, int $slotId, bool $includeUnavailable = false): array {
        self::date($date); $this->slot($slotId);
        $day = $this->db->one('SELECT * FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?', [$this->id(), $slotId, $date]);
        $params = [$this->id(), $slotId, $date];
        $condition = '(s.mode=\'date\' AND s.on_date=?)';
        if (!$day) { $condition .= ' OR (s.mode=\'weekday\' AND s.weekday=?)'; $params[] = (int)(new \DateTimeImmutable($date))->format('N') - 1; }
        $rows = $this->db->rows('SELECT i.*,s.id AS schedule_id,s.mode,s.available,s.qty_limit,s.qty_sold,COALESCE(s.price_override,i.price) AS effective_price FROM catalog_menuschedule s JOIN catalog_menuitem i ON i.id=s.item_id AND i.tenant_id=s.tenant_id WHERE s.tenant_id=? AND s.slot_id=? AND (' . $condition . ') AND i.fulfilment=\'scheduled\' ORDER BY CASE WHEN s.mode=\'date\' THEN 1 ELSE 0 END', $params);
        $chosen = [];
        foreach ($rows as $row) $chosen[(int)$row['id']] = $row;
        $result = array_filter(array_values($chosen), fn($r) => $r['active'] && ($includeUnavailable || ($r['available'] && ($r['qty_limit'] === null || $r['qty_sold'] < $r['qty_limit']))));
        usort($result, fn($a, $b) => [$a['sort'], $a['name']] <=> [$b['sort'], $b['name']]);
        return array_values($result);
    }
    public function menuRevision(string $date, int $slotId): int {
        $row = $this->db->one('SELECT revision FROM catalog_menuday WHERE tenant_id=? AND slot_id=? AND on_date=?', [$this->id(), $slotId, self::date($date)]);
        return (int)($row['revision'] ?? 0);
    }
    public function saveMenu(string $date, int $slotId, array $ids, int $revision): void {
        self::date($date); $this->slot($slotId);
        if ($date < date('Y-m-d')) throw new HttpError(422, 'Historical menus cannot be changed.');
        $ids = array_values(array_unique(array_map('intval', $ids)));
        if (count($ids) > 500) throw new HttpError(422, 'Too many selected dishes.');
        $this->db->transaction(function () use ($date, $slotId, $ids, $revision): void {
            // Serialize full-menu saves against the same store, including the first save.
            $this->db->one('SELECT id FROM tenancy_tenant WHERE id=? FOR UPDATE', [$this->id()]);
            if ($revision !== $this->menuRevision($date, $slotId)) throw new HttpError(409, 'This menu changed in another window. Reload it before saving.');
            foreach ($ids as $id) {
                $item = $this->item($id);
                if ($item['fulfilment'] !== 'scheduled' || !$item['active']) throw new HttpError(422, 'Choose active meal dishes only.');
            }
            $this->db->rows('INSERT INTO catalog_menuday(tenant_id,slot_id,on_date,revision,updated_at) VALUES(?,?,?,1,CURRENT_TIMESTAMP) ON CONFLICT(tenant_id,slot_id,on_date) DO UPDATE SET revision=catalog_menuday.revision+1,updated_at=CURRENT_TIMESTAMP', [$this->id(), $slotId, $date]);
            // Do not delete schedules or reset stock counters for a previously ordered dish.
            $this->db->rows('UPDATE catalog_menuschedule SET available=FALSE WHERE tenant_id=? AND slot_id=? AND mode=\'date\' AND on_date=?', [$this->id(), $slotId, $date]);
            foreach ($ids as $id) {
                $row = $this->db->one('SELECT id FROM catalog_menuschedule WHERE tenant_id=? AND item_id=? AND slot_id=? AND mode=\'date\' AND on_date=?', [$this->id(), $id, $slotId, $date]);
                if ($row) $this->db->rows('UPDATE catalog_menuschedule SET available=TRUE WHERE tenant_id=? AND id=?', [$this->id(), $row['id']]);
                else $this->db->rows('INSERT INTO catalog_menuschedule(tenant_id,item_id,slot_id,mode,on_date,weekday,available,qty_limit,qty_sold,price_override) VALUES(?,?,?,\'date\',?,NULL,TRUE,NULL,0,NULL)', [$this->id(), $id, $slotId, $date]);
            }
        });
    }
    public function zoneQuote(string $pincode, string $slotKey, int $subtotal, ?int $areaId = null): array {
        if (!preg_match('/^[1-9][0-9]{5}$/D', $pincode)) throw new HttpError(422, 'Enter a valid six-digit pincode.');
        $zones = $this->db->rows('SELECT * FROM delivery_deliveryzone WHERE tenant_id=? AND active AND pincode=? ORDER BY area_name', [$this->id(), $pincode]);
        $zones = array_values(array_filter($zones, function ($row) use ($slotKey) {
            $keys = json_decode($row['slot_keys'], true, 512, JSON_THROW_ON_ERROR);
            return !$keys || in_array($slotKey, $keys, true);
        }));
        if (!$zones) throw new HttpError(422, 'We do not deliver this meal to that pincode.');
        if (count($zones) > 1 && !$areaId) throw new HttpError(422, 'Choose your delivery area for this pincode.');
        $zone = null;
        foreach ($zones as $candidate) if (!$areaId || (int)$candidate['id'] === $areaId) $zone = $candidate;
        if (!$zone) throw new HttpError(422, 'Choose a valid delivery area.');
        $minimum = Money::parse($zone['min_order']);
        if ($subtotal < $minimum) throw new HttpError(422, 'Minimum food value is ' . Money::display($minimum) . '. Add ' . Money::display($minimum - $subtotal) . ' more.');
        return ['zone' => $zone, 'fee' => Money::parse($zone['delivery_fee']), 'minimum' => $minimum];
    }
}
