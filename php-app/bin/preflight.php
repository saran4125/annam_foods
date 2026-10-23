<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require dirname(__DIR__) . '/src/bootstrap.php';
use Annam\Database;
$checks = ['PHP 8.2+' => version_compare(PHP_VERSION, '8.2.0', '>='),
           'PDO PostgreSQL' => extension_loaded('pdo_pgsql'),
           'cURL' => extension_loaded('curl'), 'Multibyte strings' => extension_loaded('mbstring'), 'ZIP export' => extension_loaded('zip'),
           'OpenSSL' => extension_loaded('openssl'), 'Fileinfo' => extension_loaded('fileinfo'),
           'Private environment' => is_file(ANNAM_ROOT . '/.env'),
           'Session folder writable' => is_writable(ANNAM_ROOT . '/storage/sessions'),
           'Log folder writable' => is_writable(ANNAM_ROOT . '/storage/logs'),
           'App secret configured' => strlen(getenv('APP_SECRET') ?: '') >= 32];
try { (new Database())->one('SELECT 1'); $checks['Database connection'] = true; }
catch (Throwable $e) { $checks['Database connection'] = false; }
foreach ($checks as $label=>$passed) echo ($passed?'PASS':'FAIL') . ' ' . $label . PHP_EOL;
exit(in_array(false, $checks, true) ? 1 : 0);
