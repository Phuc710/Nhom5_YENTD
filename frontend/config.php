<?php
/**
 * config.php — Đọc .env và định nghĩa constants
 * Include ở đầu mỗi file PHP.
 */

// Đọc .env
$envFile = __DIR__ . '/.env';
if (!file_exists($envFile)) {
    $envFile = __DIR__ . '/.env.example';
}

$lines = file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
foreach ($lines as $line) {
    if (str_starts_with(trim($line), '#') || !str_contains($line, '=')) continue;
    [$key, $value] = explode('=', $line, 2);
    $_ENV[trim($key)] = trim($value);
}

// Constants
define('API_URL',   rtrim($_ENV['API_URL'] ?? 'http://localhost:8000', '/'));
define('APP_NAME',  $_ENV['APP_NAME']  ?? 'Quản lý Vi phạm');
define('TIMEZONE',  $_ENV['TIMEZONE']  ?? 'Asia/Ho_Chi_Minh');

// Múi giờ PHP
date_default_timezone_set(TIMEZONE);
