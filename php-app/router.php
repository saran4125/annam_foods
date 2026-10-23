<?php
// Development server only: php -S 127.0.0.1:8091 -t public router.php
declare(strict_types=1);
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
if (str_starts_with(rawurldecode($path), '/media/website/')) { http_response_code(404); return true; }
$file = realpath(__DIR__ . '/public' . $path);
if ($file && str_starts_with($file, __DIR__ . '/public/') && is_file($file)
    && !preg_match('/\.(php|env|ini|log|sql|dump|zip)$/i', $file)) {
    return false;
}
require __DIR__ . '/public/index.php';
