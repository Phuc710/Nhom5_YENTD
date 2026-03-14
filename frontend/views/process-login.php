<?php
use Frontend\App\Auth\Authenticator;
use Frontend\App\Auth\Session;

Session::init();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $username = $_POST['username'] ?? '';
    $password = $_POST['password'] ?? '';

    $auth = new Authenticator();
    if ($auth->login($username, $password)) {
        header('Location: /');
        exit;
    } else {
        header('Location: /login?error=invalid');
        exit;
    }
} else {
    header('Location: /login');
    exit;
}
