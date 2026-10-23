<?php
declare(strict_types=1);
// Optional temporary hosting check. No credentials, filesystem paths or phpinfo.
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow');
$postgres = extension_loaded('pdo_pgsql');
echo json_encode([
    'php_82_or_newer' => version_compare(PHP_VERSION, '8.2.0', '>='),
    'pdo_postgresql_available' => $postgres,
    'openssl_available' => extension_loaded('openssl'),
    'fileinfo_available' => extension_loaded('fileinfo'),
    'next_step' => $postgres ? 'Confirm an outbound TLS connection to the Supabase test database.'
        : 'Ask Hostinger whether this plan can enable pdo_pgsql before buying it for this application.',
], JSON_PRETTY_PRINT);
