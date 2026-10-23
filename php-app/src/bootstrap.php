<?php
declare(strict_types=1);
namespace Annam;

define('ANNAM_ROOT', dirname(__DIR__));
spl_autoload_register(function (string $class): void {
    if (str_starts_with($class, 'Annam\\')) {
        $name = substr($class, 6);
        if (preg_match('/^[A-Za-z]+$/', $name) && is_file(__DIR__ . '/' . $name . '.php')) {
            require __DIR__ . '/' . $name . '.php';
        }
    }
});
if (is_file(ANNAM_ROOT . '/.env')) {
    foreach (file(ANNAM_ROOT . '/.env', FILE_IGNORE_NEW_LINES) as $line) {
        if (!trim($line) || str_starts_with(ltrim($line), '#') || !str_contains($line, '=')) continue;
        [$key, $value] = explode('=', $line, 2);
        if (preg_match('/^[A-Z_][A-Z0-9_]*$/', $key) && getenv($key) === false) {
            putenv($key . '=' . trim($value, "\"'\r\n"));
        }
    }
}
date_default_timezone_set(getenv('APP_TIMEZONE') ?: 'Asia/Kolkata');
error_reporting(E_ALL);
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('zend.exception_ignore_args', '1');
ini_set('error_log', ANNAM_ROOT . '/storage/logs/php.log');

function e(mixed $value): string { return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function money(mixed $value): string { return Money::display(Money::parse((string)$value)); }
function csrf(): string { return '<input type="hidden" name="csrf" value="' . e(Security::csrf()) . '">'; }
function redirect(string $url): never {
    if (!str_starts_with($url, '/') || str_starts_with($url, '//') || str_contains($url, "\r") || str_contains($url, "\n")) $url = '/';
    header('Location: ' . $url, true, 303); exit;
}
function image_url(?string $name): string {
    if (!$name) return '';
    if (str_contains($name, '..') || str_contains($name, '\\')) return '';
    if (str_starts_with($name, '/media/')) return $name;
    if (str_starts_with($name, '/') || str_contains($name, '://')) return '';
    return '/media/' . implode('/', array_map('rawurlencode', explode('/', $name)));
}
