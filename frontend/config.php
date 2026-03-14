<?php
/**
 * config.php - Đọc .env và định nghĩa constants động cho frontend.
 */

$envFile = __DIR__ . '/.env';
if (!file_exists($envFile)) {
    $envFile = __DIR__ . '/.env.example';
}

$lines = file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
foreach ($lines as $line) {
    if (str_starts_with(trim($line), '#') || !str_contains($line, '=')) {
        continue;
    }

    [$key, $value] = explode('=', $line, 2);
    $value = trim($value);
    $value = trim($value, "\"'");
    $_ENV[trim($key)] = $value;
}

function current_origin(): string
{
    $scheme = 'http';
    if (!empty($_SERVER['HTTP_X_FORWARDED_PROTO'])) {
        $scheme = explode(',', $_SERVER['HTTP_X_FORWARDED_PROTO'])[0];
    } elseif (
        (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
        || (($_SERVER['SERVER_PORT'] ?? null) == 443)
    ) {
        $scheme = 'https';
    }

    $host = $_SERVER['HTTP_X_FORWARDED_HOST']
        ?? $_SERVER['HTTP_HOST']
        ?? 'localhost';

    return $scheme . '://' . $host;
}

function is_local_origin(string $origin): bool
{
    $host = parse_url($origin, PHP_URL_HOST) ?: '';
    return in_array($host, ['localhost', '127.0.0.1'], true);
}

$apiUrl = trim($_ENV['API_URL'] ?? '');
if ($apiUrl === '') {
    $currentOrigin = current_origin();
    $apiUrl = $currentOrigin;

    if (!is_local_origin($currentOrigin)) {
        error_log('frontend/config.php: API_URL is empty on a non-local origin; defaulting to same-origin API.');
    }
}

define('API_URL', rtrim($apiUrl, '/'));
define('APP_NAME', $_ENV['APP_NAME'] ?? 'Quan ly Vi pham');
define('TIMEZONE', $_ENV['TIMEZONE'] ?? 'Asia/Ho_Chi_Minh');

date_default_timezone_set(TIMEZONE);
