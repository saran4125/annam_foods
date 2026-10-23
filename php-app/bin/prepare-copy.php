<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require dirname(__DIR__) . '/src/bootstrap.php';
use Annam\Database;
if (!in_array('--confirm-test-copy', $argv, true)) {
    fwrite(STDERR, "Run only against a separate test database, with --confirm-test-copy.\n"); exit(1);
}
$db = new Database();
$db->rows('CREATE TABLE IF NOT EXISTS php_login_attempt(id bigserial PRIMARY KEY,tenant_id bigint NOT NULL REFERENCES tenancy_tenant(id),fingerprint varchar(64) NOT NULL,attempted_at timestamptz NOT NULL)');
$db->rows('CREATE INDEX IF NOT EXISTS php_login_attempt_scope ON php_login_attempt(tenant_id,fingerprint,attempted_at)');
$media = getenv('MEDIA_ROOT') ?: 'public/media';
if (!str_starts_with($media, '/')) $media = ANNAM_ROOT . '/' . $media;
if (!is_dir($media . '/brand')) mkdir($media . '/brand', 0750, true);
if (!is_file($media . '/brand/annam-logo.png')) copy(ANNAM_ROOT . '/resources/media/brand/annam-logo.png', $media . '/brand/annam-logo.png');
if (!is_file($media . '/.htaccess')) copy(ANNAM_ROOT . '/deploy/media.htaccess', $media . '/.htaccess');
echo "PHP sign-in protection prepared. No existing store data was modified.\n";
