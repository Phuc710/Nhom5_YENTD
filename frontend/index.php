<?php
/**
 * Camera AI - Local Monitor
 * Professional Entry Point (OOP Architecture)
 */

require_once __DIR__ . '/src/Core/Config.php';
require_once __DIR__ . '/src/Core/View.php';

use App\Core\Config;
use App\Core\View;

// CLI Server Static File Handling
if (PHP_SAPI === 'cli-server') {
    $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
    if ($path !== '/' && is_file(__DIR__ . $path)) {
        return false;
    }
}

// 1. Load Configuration
Config::load(dirname(__DIR__) . '/backend/.env');
Config::load(__DIR__ . '/.env');

// 2. Resolve API Base URL
$requestHost = $_SERVER['HTTP_HOST'] ?? '127.0.0.1:8080';
$hostOnly = parse_url('//' . $requestHost, PHP_URL_HOST) ?: '127.0.0.1';
$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$defaultApiBaseUrl = "{$scheme}://{$hostOnly}:8000";
$requestUri = $_SERVER['REQUEST_URI'] ?? '/';
$currentPath = parse_url($requestUri, PHP_URL_PATH) ?: '/';

$apiBaseUrl = Config::getApiBaseUrl($defaultApiBaseUrl);

// 3. Render View
View::render('layout', [
    'title' => 'Camera AI',
    'apiBaseUrl' => $apiBaseUrl,
    'currentPath' => $currentPath,
]);
