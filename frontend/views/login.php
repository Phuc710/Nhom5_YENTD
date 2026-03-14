<?php
use Frontend\App\Auth\Session;

Session::init();

if (Session::isLoggedIn()) {
    header('Location: /');
    exit;
}

$error = $_GET['error'] ?? '';
?>
<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Đăng nhập | YTD Monitoring</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --color-bg: #0b0e14;
            --color-primary: #3b82f6;
            --color-error: #ef4444;
            --color-text: #f8fafc;
            --color-text-dim: #94a3b8;
            --blur-glass: 20px;
            --border-glass: 1px solid rgba(255, 255, 255, 0.1);
        }

        body {
            margin: 0;
            padding: 0;
            background: var(--color-bg);
            font-family: 'Inter', sans-serif;
            color: var(--color-text);
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            overflow: hidden;
        }

        .login-bg {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 20% 30%, rgba(59, 130, 246, 0.2) 0%, transparent 40%),
                radial-gradient(circle at 80% 70%, rgba(59, 130, 246, 0.1) 0%, transparent 40%);
            z-index: -1;
        }

        .login-card {
            width: 100%;
            max-width: 400px;
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(var(--blur-glass));
            border: var(--border-glass);
            border-radius: 24px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }

        .login-header {
            text-align: center;
            margin-bottom: 32px;
        }

        .brand-logo {
            width: 60px;
            height: 60px;
            background: var(--color-primary);
            border-radius: 16px;
            margin: 0 auto 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: 0 0 20px rgba(59, 130, 246, 0.5);
        }

        .login-title {
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            margin: 0;
        }

        .login-subtitle {
            font-size: 0.875rem;
            color: var(--color-text-dim);
            margin-top: 8px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .form-label {
            display: block;
            font-size: 0.75rem;
            font-weight: 700;
            color: var(--color-text-dim);
            text-transform: uppercase;
            margin-bottom: 8px;
        }

        .form-input {
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 12px 16px;
            color: #fff;
            font-size: 1rem;
            transition: all 0.2s;
            box-sizing: border-box;
        }

        .form-input:focus {
            outline: none;
            border-color: var(--color-primary);
            background: rgba(59, 130, 246, 0.05);
        }

        .btn-login {
            width: 100%;
            background: var(--color-primary);
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            color: #fff;
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            margin-top: 8px;
        }

        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(37, 99, 235, 0.3);
        }

        .error-msg {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.2);
            color: var(--color-error);
            padding: 12px;
            border-radius: 10px;
            font-size: 0.875rem;
            margin-bottom: 24px;
            text-align: center;
        }
    </style>
</head>

<body>
    <div class="login-bg"></div>
    <div class="login-card">
        <div class="login-header">
            <div class="brand-logo">🛡️</div>
            <h1 class="login-title">YTD Monitoring</h1>
            <p class="login-subtitle">Hệ thống giám sát vi phạm tập trung</p>
        </div>

        <?php if ($error === 'invalid'): ?>
            <div class="error-msg">Tài khoản hoặc mật khẩu không đúng.</div>
        <?php endif; ?>

        <form action="/process-login" method="POST">
            <div class="form-group">
                <label class="form-label">Tài khoản</label>
                <input type="text" name="username" class="form-input" placeholder="Tên đăng nhập" required
                    autocomplete="username">
            </div>
            <div class="form-group">
                <label class="form-label">Mật khẩu</label>
                <input type="password" name="password" class="form-input" placeholder="••••••••" required
                    autocomplete="current-password">
            </div>
            <button type="submit" class="btn-login">Đăng nhập</button>
        </form>
    </div>
</body>

</html>