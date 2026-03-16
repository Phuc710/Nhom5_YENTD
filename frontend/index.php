<?php
// Core logic for PHP built-in server
if (php_sapi_name() === 'cli-server') {
    $path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
    if (file_exists(__DIR__ . $path) && is_file(__DIR__ . $path)) {
        return false;
    }
}

require_once __DIR__ . '/bootstrap.php';

use Frontend\App\Core\Router;

$router = new Router();

// Route cho trang chu (Danh sach camera)
$router->add('/', 'dashboard');

// Route cho trang chi tiet camera
$router->add('/camera/{id}', 'camera-detail');

// Route cho trang chi tiet vi pham
$router->add('/violation/{id}', 'violation-detail');

// Route cho danh sach vi pham
$router->add('/violations', 'violations');

// Route cho danh sach camera (admin)
$router->add('/cameras', 'cameras');

// Route Cài đặt hệ thống
$router->add('/settings', 'settings');

// Route Báo cáo & Phân tích
$router->add('/reports', 'reports');
$router->add('/analytics', 'analytics');

// Route Auth
$router->add('/login', 'login');
$router->add('/logout', 'logout');
$router->add('/process-login', 'process-login');

$router->dispatch();
