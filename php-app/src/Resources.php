<?php
declare(strict_types=1);
namespace Annam;

final class Resources {
    public const DEFINITIONS = [
        'dishes' => ['table' => 'catalog_menuitem', 'title' => 'Dishes & products', 'fields' => [
            'name' => 'Name|text', 'fulfilment' => 'Type|fulfilment', 'category_id' => 'Category|category',
            'price' => 'Price (₹)|price', 'description' => 'Description|textarea', 'active' => 'On sale|bool',
            'is_veg' => 'Vegetarian|bool', 'sort' => 'Display order|int'],
            'defaults' => ['retailer_id' => null, 'tax_rate' => null, 'sac' => '', 'tags' => '[]', 'image' => '']],
        'categories' => ['table' => 'catalog_menucategory', 'title' => 'Categories', 'fields' => [
            'name' => 'Name|text', 'slug' => 'URL name|slug', 'description' => 'Description|textarea',
            'active' => 'Show category|bool', 'sort' => 'Display order|int'], 'defaults' => ['parent_id' => null, 'image' => '']],
        'zones' => ['table' => 'delivery_deliveryzone', 'title' => 'Delivery areas', 'fields' => [
            'area_name' => 'Area name|text', 'pincode' => 'Pincode|pincode', 'delivery_fee' => 'Delivery charge (₹)|price',
            'min_order' => 'Minimum food value (₹)|price', 'slot_keys' => 'Meals served|slots', 'active' => 'Delivering|bool'], 'defaults' => []],
        'slots' => ['table' => 'catalog_slot', 'title' => 'Meal times', 'fields' => [
            'label' => 'Meal name|text', 'key' => 'Meal key|slug', 'order_cutoff' => 'Orders close|time',
            'delivery_from' => 'Delivery starts|optional_time', 'delivery_to' => 'Delivery ends|optional_time',
            'sort' => 'Display order|int', 'active' => 'Available|bool'], 'defaults' => []],
        'banners' => ['table' => 'content_banner', 'title' => 'Offer banners', 'fields' => [
            'title' => 'Heading|text', 'subtitle' => 'Message|optional_text', 'link' => 'Button link|link',
            'sort' => 'Display order|int', 'active' => 'Show banner|bool'], 'defaults' => ['image' => '']],
        'pages' => ['table' => 'content_page', 'title' => 'Website pages', 'fields' => [
            'title' => 'Title|text', 'slug' => 'URL name|slug', 'body_md' => 'Content|textarea',
            'seo_description' => 'Search description|optional_text', 'published' => 'Publish page|bool',
            'show_in_nav' => 'Show in navigation|bool', 'sort' => 'Display order|int'], 'defaults' => []],
    ];
    public function __construct(private Store $store) {}
    public static function definition(string $key): array { return self::DEFINITIONS[$key] ?? throw new HttpError(404, 'Page not found.'); }
    public function list(string $key): array {
        $spec = self::definition($key);
        $order = match ($key) { 'zones' => 'pincode,area_name', 'slots' => 'sort,key', 'pages', 'banners' => 'sort,title', default => 'sort,name' };
        return $this->store->db->rows('SELECT * FROM ' . $spec['table'] . ' WHERE tenant_id=? ORDER BY ' . $order, [$this->store->id()]);
    }
    public function get(string $key, int $id): array {
        $spec = self::definition($key);
        return $this->store->db->one('SELECT * FROM ' . $spec['table'] . ' WHERE tenant_id=? AND id=?', [$this->store->id(), $id]) ?? throw new HttpError(404, 'Record not found.');
    }
    public function save(string $key, ?int $id, array $input, array $files = []): int {
        $spec = self::definition($key);
        $existing = $id ? $this->get($key, $id) : [];
        $values = [];
        foreach ($spec['fields'] as $field => $definition) {
            [$label, $type] = explode('|', $definition);
            $raw = $input[$field] ?? '';
            if ($type !== 'slots' && !is_scalar($raw)) throw new HttpError(422, 'Invalid ' . $label . '.');
            $raw = is_string($raw) ? trim($raw) : $raw;
            $value = match ($type) {
                'bool' => !empty($raw),
                'price' => Money::decimal(Money::parse((string)$raw)),
                'category' => $raw === '' ? null : (int)$raw,
                'int' => filter_var($raw === '' ? '0' : $raw, FILTER_VALIDATE_INT),
                'slots' => json_encode($this->slotKeys($raw), JSON_THROW_ON_ERROR),
                default => (string)$raw,
            };
            if ($type === 'text' && ($value === '' || strlen($value) > 140)) throw new HttpError(422, $label . ' is required (up to 140 characters).');
            if ($type === 'slug' && !preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/D', $value)) throw new HttpError(422, 'Use lowercase letters, numbers and hyphens for ' . $label . '.');
            if ($type === 'pincode' && !preg_match('/^[1-9][0-9]{5}$/D', $value)) throw new HttpError(422, 'Enter an exact six-digit pincode.');
            if ($type === 'int' && ($value === false || $value < 0 || $value > 32767)) throw new HttpError(422, 'Enter a whole number between 0 and 32767.');
            if ($type === 'price' && Money::parse($value) > 99999999) throw new HttpError(422, 'Amount is too large.');
            if ($type === 'fulfilment' && !in_array($value, ['scheduled', 'courier'], true)) throw new HttpError(422, 'Choose Meals or Other items.');
            if ($type === 'link' && $value !== '' && !preg_match('~^(?:/(?!/)[^\\\\]*|https://[^\s]+)$~D', $value)) throw new HttpError(422, 'Use a local website path or an HTTPS link.');
            if ($type === 'time' || $type === 'optional_time') {
                if ($type === 'optional_time' && $value === '') $value = null;
                elseif (!preg_match('/^(?:[01][0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?$/D', $value)) throw new HttpError(422, 'Enter a valid ' . $label . '.');
            }
            if ($type === 'category' && $value !== null && !$this->store->db->one('SELECT id FROM catalog_menucategory WHERE tenant_id=? AND id=?', [$this->store->id(), $value])) throw new HttpError(422, 'Choose a category from this store.');
            if (is_string($value) && strlen($value) > ($type === 'textarea' ? 50000 : 300)) throw new HttpError(422, $label . ' is too long.');
            $values[$field] = $value;
        }
        if (array_key_exists('image', $spec['defaults']) && ($files['image']['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_NO_FILE) {
            $values['image'] = self::upload($files['image'], match ($key) { 'categories' => 'categories', 'banners' => 'banners', default => 'menu' });
        }
        if ($key === 'pages') $values['updated_at'] = date('c');
        if($key==='dishes'){
            $tags=$existing?json_decode($existing['tags'],true,64,JSON_THROW_ON_ERROR):[];$tags=array_values(array_filter($tags,fn($tag)=>$tag!=='featured'));if(!empty($input['featured']))$tags[]='featured';$values['tags']=json_encode($tags,JSON_THROW_ON_ERROR);
        }
        if ($id) {
            $sets = implode(',', array_map(fn($field) => '"' . $field . '"=?', array_keys($values)));
            $this->store->db->rows('UPDATE ' . $spec['table'] . ' SET ' . $sets . ' WHERE tenant_id=? AND id=?', [...array_values($values), $this->store->id(), $id]);
            return $id;
        }
        $values = ['tenant_id' => $this->store->id(), ...$spec['defaults'], ...$values];
        $columns = implode(',', array_map(fn($field) => '"' . $field . '"', array_keys($values)));
        $row = $this->store->db->one('INSERT INTO ' . $spec['table'] . '(' . $columns . ') VALUES(' . implode(',', array_fill(0, count($values), '?')) . ') RETURNING id', array_values($values));
        return (int)$row['id'];
    }
    private function slotKeys(mixed $value): array {
        if (!is_array($value)) $value = [];
        $keys = array_values(array_unique(array_map('strval', $value)));
        foreach ($keys as $key) if (!in_array($key, ['breakfast', 'lunch', 'dinner', 'snacks'], true)) throw new HttpError(422, 'Choose valid meals.');
        if (!$keys) throw new HttpError(422, 'Select at least one meal for this delivery area.');
        return $keys;
    }
    public function toggle(string $key, int $id): void {
        $spec = self::definition($key); $this->get($key, $id);
        $field = $key === 'pages' ? 'published' : 'active';
        $this->store->db->rows('UPDATE ' . $spec['table'] . ' SET ' . $field . '=NOT ' . $field . ' WHERE tenant_id=? AND id=?', [$this->store->id(), $id]);
    }
    public function removeFromSale(string $key, int $id): void {
        $spec = self::definition($key); $this->get($key, $id);
        $field = $key === 'pages' ? 'published' : 'active';
        // Archive rather than deleting products referenced by old orders or menus.
        $this->store->db->rows('UPDATE ' . $spec['table'] . ' SET ' . $field . '=FALSE WHERE tenant_id=? AND id=?', [$this->store->id(), $id]);
    }
    public static function upload(array $file, string $folder): string {
        if ($file['error'] !== UPLOAD_ERR_OK || $file['size'] > 3 * 1024 * 1024 || !is_uploaded_file($file['tmp_name'])) throw new HttpError(422, 'Choose an image smaller than 3 MB.');
        $size = getimagesize($file['tmp_name']);
        $extension = $size ? ([IMAGETYPE_JPEG => '.jpg', IMAGETYPE_PNG => '.png', IMAGETYPE_WEBP => '.webp'][$size[2]] ?? null) : null;
        if (!$extension || $size[0] * $size[1] > 25000000) throw new HttpError(422, 'Choose a JPG, PNG or WebP image up to 25 megapixels.');
        $root = getenv('MEDIA_ROOT') ?: 'public/media';
        if (!str_starts_with($root, '/')) $root = ANNAM_ROOT . '/' . $root;
        $relative = $folder . '/' . bin2hex(random_bytes(20)) . $extension;
        if (!is_dir($root . '/' . $folder) && !mkdir($root . '/' . $folder, 0750, true)) throw new \RuntimeException('Cannot create media folder.');
        if (!move_uploaded_file($file['tmp_name'], $root . '/' . $relative)) throw new \RuntimeException('Cannot save uploaded image.');
        return $relative;
    }
}
