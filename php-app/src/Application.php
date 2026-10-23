<?php
declare(strict_types=1);
namespace Annam;

final class Application {
    private Database $db;
    private Store $store;
    private ?array $user = null;
    public static function run(): void {
        try { (new self())->handle(); }
        catch (HttpError $error) { http_response_code($error->status); self::error($error->getMessage()); }
        catch (\Throwable $error) {
            error_log($error->__toString()); http_response_code(503);
            self::error('The PHP preview could not start. Check the private server log and environment settings.');
        }
    }
    private static function error(string $message): void {
        echo '<!doctype html><meta charset="utf-8"><title>Annam Foods</title><main style="font:18px system-ui;max-width:640px;margin:80px auto;padding:24px"><h1>Annam Foods</h1><p>' . e($message) . '</p><p><a href="javascript:history.back()">Go back</a> · <a href="/">Home</a></p></main>';
    }
    private function handle(): void {
        if (!in_array(getenv('APP_ENV') ?: 'local', ['local', 'preview'], true)) throw new HttpError(503, 'The PHP rebuild is not yet approved for production.');
        $expected = parse_url(getenv('APP_URL') ?: 'http://127.0.0.1:8091', PHP_URL_HOST);
        $rawHost = $_SERVER['HTTP_HOST'] ?? '';
        if (!preg_match('/^[a-zA-Z0-9.:[\]-]+$/D', $rawHost)) throw new HttpError(404, 'Unknown store hostname.');
        $host = parse_url('http://' . $rawHost, PHP_URL_HOST);
        if (!$host || strtolower($host) !== strtolower($expected)) throw new HttpError(404, 'Unknown store hostname.');
        Security::start();
        $this->db = new Database();
        $path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
        $method = $_SERVER['REQUEST_METHOD'];
        if ($path === '/healthz') { $this->db->one('SELECT 1'); header('Content-Type: application/json'); echo '{"status":"ok","application":"php-preview"}'; return; }
        $this->store = new Store($this->db);
        $this->user = Security::user($this->db, $this->store);
        if (!in_array($method, ['GET', 'POST'], true)) throw new HttpError(405, 'Method not allowed.');
        if ($method === 'POST') Security::verifyCsrf();

        if ($path === '/manage/login/') {
            $error = '';
            if ($method === 'POST') {
                if (Security::login($this->db, $this->store, (string)($_POST['username'] ?? ''), (string)($_POST['password'] ?? ''))) redirect('/manage/');
                $error = 'The username or password is incorrect, or this account has no store access.';
            }
            $this->render('login', compact('error'), false); return;
        }
        if (str_starts_with($path, '/manage/')) {
            if (!$this->user) redirect('/manage/login/');
            $this->admin($path, $method); return;
        }
        if ($path === '/cart/add/' && $method === 'POST') {
            Cart::add($this->store, $_POST); $_SESSION['notice'] = 'Added to your cart.'; redirect('/cart/');
        }
        if ($path === '/cart/clear/' && $method === 'POST') { unset($_SESSION['cart']); redirect('/cart/'); }
        if ($path === '/cart/remove/' && $method === 'POST') { unset($_SESSION['cart']['lines'][(int)($_POST['item_id'] ?? 0)]); redirect('/cart/'); }
        if ($method !== 'GET' && $path !== '/cart/') throw new HttpError(405, 'Method not allowed.');
        if ($path === '/') {
            $slots = $this->store->slots(); $date = date('Y-m-d'); $menus = [];
            foreach ($slots as $slot) $menus[] = ['slot' => $slot, 'items' => $this->store->menu($date, (int)$slot['id'])];
            $products = array_slice(array_filter($this->store->items('courier'), fn($i) => $i['active']), 0, 8);
            $banners = $this->db->rows('SELECT * FROM content_banner WHERE tenant_id=? AND active ORDER BY sort,id LIMIT 3', [$this->store->id()]);
            $this->render('home', compact('menus', 'products', 'banners', 'date')); return;
        }
        if ($path === '/menu/') {
            $date = Store::date((string)($_GET['date'] ?? date('Y-m-d'))); $menus = [];
            foreach ($this->store->slots() as $slot) $menus[] = ['slot' => $slot, 'items' => $this->store->menu($date, (int)$slot['id'], true)];
            $this->render('menu', compact('menus', 'date')); return;
        }
        if (preg_match('~^/shop/(?:([a-z0-9-]+)/)?$~', $path, $match)) {
            $category = null;
            if (!empty($match[1])) {
                $category = $this->db->one('SELECT * FROM catalog_menucategory WHERE tenant_id=? AND slug=? AND active', [$this->store->id(), $match[1]]) ?? throw new HttpError(404, 'Category not found.');
            }
            $query = trim((string)($_GET['q'] ?? ''));
            $products = array_values(array_filter($this->store->items('courier', $query, $category ? (int)$category['id'] : null), fn($i) => $i['active']));
            $this->render('shop', compact('products', 'category', 'query')); return;
        }
        if (preg_match('~^/item/(\d+)/$~', $path, $match)) {
            $item = $this->store->item((int)$match[1]);
            if (!$item['active']) throw new HttpError(404, 'Item not available.');
            $this->render('item', compact('item')); return;
        }
        if ($path === '/cart/') {
            $quote = Cart::quote($this->store); $delivery = null; $error = '';
            if ($method === 'POST' && $quote['lines']) {
                try {
                    $subtotal = $quote['subtotal'];
                    if ($quote['cart']['kind'] === 'scheduled') {
                        $slot = $this->store->slot($quote['cart']['slot_id']);
                        $delivery = $this->store->zoneQuote(trim((string)($_POST['pincode'] ?? '')), $slot['key'], $subtotal, !empty($_POST['area_id']) ? (int)$_POST['area_id'] : null);
                    } else {
                        $settings = $this->store->config['checkout_settings'];
                        $pin = trim((string)($_POST['pincode'] ?? ''));
                        if (!($settings['courier_enabled'] ?? false) || !in_array($pin, $settings['courier_pincodes'] ?? [], true)) throw new HttpError(422, 'Courier delivery is not available for that pincode.');
                        $minimum = Money::parse((string)($settings['courier_minimum'] ?? '0'));
                        if ($subtotal < $minimum) throw new HttpError(422, 'Minimum shop items value is ' . Money::display($minimum) . '.');
                        $delivery = ['fee' => Money::parse((string)($settings['courier_fee'] ?? '0')), 'minimum' => $minimum];
                    }
                } catch (HttpError $e) { $error = $e->getMessage(); }
            }
            $areas = $this->db->rows('SELECT id,area_name,pincode FROM delivery_deliveryzone WHERE tenant_id=? AND active ORDER BY area_name', [$this->store->id()]);
            $this->render('cart', compact('quote', 'delivery', 'error', 'areas')); return;
        }
        if ($path === '/about/' || preg_match('~^/p/([a-z0-9-]+)/$~', $path, $match)) {
            $slug = $path === '/about/' ? 'about' : $match[1];
            $page = $this->db->one('SELECT * FROM content_page WHERE tenant_id=? AND published AND slug=?', [$this->store->id(), $slug]) ?? throw new HttpError(404, 'Page not found.');
            $this->render('page', compact('page')); return;
        }
        throw new HttpError(404, 'Page not found.');
    }
    private function admin(string $path, string $method): void {
        $resources = new Resources($this->store);
        if ($path === '/manage/logout/' && $method === 'POST') { $_SESSION = []; session_regenerate_id(true); redirect('/manage/login/'); }
        if ($path === '/manage/') {
            $items = $this->store->items(); $date = date('Y-m-d'); $menus = [];
            foreach ($this->store->slots() as $slot) $menus[] = ['slot' => $slot, 'items' => $this->store->menu($date, (int)$slot['id'])];
            $this->render('dashboard', compact('items', 'date', 'menus'), true); return;
        }
        if ($path === '/manage/dishes/menu/') {
            $slots = $this->store->slots();
            $date = Store::date((string)($_POST['date'] ?? $_GET['date'] ?? date('Y-m-d')));
            $slotId = (int)($_POST['slot_id'] ?? $_GET['slot_id'] ?? ($slots[0]['id'] ?? 0));
            $slot = $this->store->slot($slotId);
            if ($method === 'POST') {
                $this->store->saveMenu($date, $slotId, (array)($_POST['items'] ?? []), (int)($_POST['revision'] ?? -1));
                $_SESSION['notice'] = 'Menu saved for ' . $date . ' · ' . $slot['label'] . '.';
                redirect('/manage/dishes/menu/?date=' . $date . '&slot_id=' . $slotId);
            }
            $entries = $this->store->menu($date, $slotId, true);
            $selected = array_column(array_filter($entries, fn($i) => $i['available']), 'id');
            $items = $this->store->items('scheduled'); $revision = $this->store->menuRevision($date, $slotId);
            $this->render('daily-menu', compact('date', 'slots', 'slot', 'slotId', 'selected', 'items', 'revision'), true); return;
        }
        if ($path === '/manage/settings/') {
            if ($method === 'POST') {
                $name = trim((string)($_POST['brand_name'] ?? ''));
                $phone = trim((string)($_POST['support_phone'] ?? ''));
                $tagline = trim((string)($_POST['tagline'] ?? ''));
                if (!$name || strlen($name) > 120 || strlen($phone) > 30 || strlen($tagline) > 200) throw new HttpError(422, 'Check the store name, tagline and phone number.');
                $this->db->transaction(function () use ($name, $tagline, $phone) {
                    $config = $this->db->one('SELECT theme FROM tenancy_tenantconfig WHERE tenant_id=? FOR UPDATE', [$this->store->id()]);
                    $theme = json_decode($config['theme'], true, 512, JSON_THROW_ON_ERROR);
                    $email = trim((string)($_POST['contact_email'] ?? ''));
                    if ($email && !filter_var($email, FILTER_VALIDATE_EMAIL)) throw new HttpError(422, 'Enter a valid email address.');
                    $theme['contact_email'] = $email;
                    if (($_FILES['logo']['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_NO_FILE) $theme['logo_url'] = '/media/' . Resources::upload($_FILES['logo'], 'brand');
                    $this->db->rows('UPDATE tenancy_tenantconfig SET brand_name=?,tagline=?,support_phone=?,theme=? WHERE tenant_id=?', [$name, $tagline, $phone, json_encode($theme, JSON_THROW_ON_ERROR), $this->store->id()]);
                });
                $_SESSION['notice'] = 'Store settings saved.'; redirect('/manage/settings/');
            }
            $this->render('settings', [], true); return;
        }
        if (preg_match('~^/manage/([a-z-]+)/(new|\d+)/(toggle|archive)/$~', $path, $match)) {
            if ($method !== 'POST') throw new HttpError(405, 'Use the action button.');
            if ($match[3] === 'toggle') $resources->toggle($match[1], (int)$match[2]);
            else $resources->removeFromSale($match[1], (int)$match[2]);
            redirect('/manage/' . $match[1] . '/');
        }
        if (preg_match('~^/manage/([a-z-]+)/(new|\d+)/$~', $path, $match)) {
            $key = $match[1]; $spec = Resources::definition($key); $id = $match[2] === 'new' ? null : (int)$match[2];
            if ($method === 'POST') {
                $resources->save($key, $id, $_POST, $_FILES); $_SESSION['notice'] = 'Saved successfully.'; redirect('/manage/' . $key . '/');
            }
            $record = $id ? $resources->get($key, $id) : ['active' => true, 'is_veg' => true, 'sort' => 0, 'price' => '0', 'delivery_fee' => '0', 'min_order' => '0', 'fulfilment' => $_GET['kind'] ?? 'scheduled'];
            $this->render('resource-edit', compact('key', 'spec', 'id', 'record'), true); return;
        }
        if (preg_match('~^/manage/([a-z-]+)/$~', $path, $match) && isset(Resources::DEFINITIONS[$match[1]])) {
            $key = $match[1]; $spec = Resources::definition($key); $records = $resources->list($key);
            $kind = $_GET['kind'] ?? 'scheduled';
            if ($key === 'dishes') $records = array_values(array_filter($records, fn($row) => $row['fulfilment'] === $kind));
            $query = trim((string)($_GET['q'] ?? ''));
            if ($query) $records = array_values(array_filter($records, fn($r) => stripos(implode(' ', array_filter($r, 'is_scalar')), $query) !== false));
            $this->render('resource-list', compact('key', 'spec', 'records', 'kind', 'query'), true); return;
        }
        throw new HttpError(404, 'This management page has not yet been migrated to the PHP preview.');
    }
    private function render(string $view, array $data = [], ?bool $admin = false): void {
        $store = $this->store; $user = $this->user; $path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
        $notice = $_SESSION['notice'] ?? ''; unset($_SESSION['notice']);
        extract($data, EXTR_SKIP);
        ob_start(); require ANNAM_ROOT . '/views/' . $view . '.php'; $content = ob_get_clean();
        if ($view === 'login') { echo $content; return; }
        require ANNAM_ROOT . '/views/' . ($admin ? 'admin-layout' : 'store-layout') . '.php';
    }
}
