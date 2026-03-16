<?php
use Frontend\App\Auth\Session;

Session::init();

header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'message' => 'Invalid request']);
    exit;
}

$username = $_POST['username'] ?? '';
$password = $_POST['password'] ?? '';

// Kiểm tra tài khoản dựa trên cấu hình .env
if ($username === ADMIN_USER && $password === ADMIN_PASS) {
    Session::set('user_id', 1);
    Session::set('username', 'admin');
    Session::set('role', 'admin');
    Session::set('is_logged_in', true);

    echo json_encode(['success' => true]);
} else {
    http_response_code(401);
    echo json_encode(['success' => false, 'message' => 'Sai tài khoản hoặc mật khẩu']);
}
exit;
