<?php
declare(strict_types=1);
namespace Annam;

final class Security {
    public static function start(): void {
        $secret = getenv('APP_SECRET') ?: '';
        if (strlen($secret) < 32) throw new \RuntimeException('Set APP_SECRET to at least 32 random characters.');
        $secure = str_starts_with(getenv('APP_URL') ?: '', 'https://');
        ini_set('session.use_strict_mode', '1');
        session_save_path(ANNAM_ROOT . '/storage/sessions');
        session_name('annam_php_session');
        session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => $secure, 'httponly' => true, 'samesite' => 'Lax']);
        session_start();
        header('X-Content-Type-Options: nosniff');
        header('X-Frame-Options: SAMEORIGIN');
        header('Referrer-Policy: same-origin');
        header('Cache-Control: private, no-store');
    }
    public static function csrf(): string { return $_SESSION['csrf'] ??= bin2hex(random_bytes(32)); }
    public static function verifyCsrf(): void {
        if (!is_string($_POST['csrf'] ?? null) || !hash_equals(self::csrf(), $_POST['csrf'])) {
            throw new HttpError(403, 'Your session expired. Refresh the page and try again.');
        }
    }
    public static function verifyPassword(string $password, string $encoded): bool {
        if (strlen($password) > 1024) return false;
        if (str_starts_with($encoded, 'pbkdf2_sha256$')) {
            $parts = explode('$', $encoded);
            if (count($parts) !== 4 || !ctype_digit($parts[1]) || (int)$parts[1] < 1 || (int)$parts[1] > 5000000) return false;
            return hash_equals($parts[3], base64_encode(hash_pbkdf2('sha256', $password, $parts[2], (int)$parts[1], 32, true)));
        }
        return password_verify($password, $encoded);
    }
    public static function login(Database $db, Store $store, string $username, string $password): bool {
        // Persistent store-scoped throttle; does not rely on a browser cookie.
        $key = hash_hmac('sha256', strtolower($username) . '|' . ($_SERVER['REMOTE_ADDR'] ?? ''), getenv('APP_SECRET'));
        $attempt = $db->one('SELECT count(*) AS attempts FROM php_login_attempt WHERE tenant_id=? AND fingerprint=? AND attempted_at > CURRENT_TIMESTAMP - INTERVAL \'15 minutes\'', [$store->id(), $key]);
        if ((int)$attempt['attempts'] >= 10) throw new HttpError(429, 'Too many sign-in attempts. Try again in 15 minutes.');
        $user = $db->one('SELECT u.id,u.username,u.password,u.is_superuser FROM auth_user u WHERE u.username=? AND u.is_active AND (u.is_superuser OR EXISTS (SELECT 1 FROM tenancy_tenantuser m WHERE m.user_id=u.id AND m.tenant_id=?))', [$username, $store->id()]);
        if (!$user || !self::verifyPassword($password, $user['password'])) {
            $db->rows('INSERT INTO php_login_attempt(tenant_id,fingerprint,attempted_at) VALUES(?,?,CURRENT_TIMESTAMP)', [$store->id(), $key]);
            // Comparable PBKDF2 work for unknown usernames; no account-existence message.
            if (!$user) self::verifyPassword($password, 'pbkdf2_sha256$1000000$annam-dummy-salt$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=');
            return false;
        }
        session_regenerate_id(true);
        $_SESSION['user_id'] = (int)$user['id'];
        $_SESSION['csrf'] = bin2hex(random_bytes(32));
        $db->rows('DELETE FROM php_login_attempt WHERE tenant_id=? AND fingerprint=?', [$store->id(), $key]);
        return true;
    }
    public static function user(Database $db, Store $store): ?array {
        if (empty($_SESSION['user_id'])) return null;
        return $db->one('SELECT u.id,u.username,u.is_superuser,m.role FROM auth_user u LEFT JOIN tenancy_tenantuser m ON m.user_id=u.id AND m.tenant_id=? WHERE u.id=? AND u.is_active AND (u.is_superuser OR m.id IS NOT NULL)', [$store->id(), (int)$_SESSION['user_id']]);
    }
}
