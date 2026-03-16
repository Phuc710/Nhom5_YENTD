<?php
use Frontend\App\Auth\Session;

Session::init();
if (Session::isLoggedIn()) {
    header("Location: /");
    exit;
}

?>
<!DOCTYPE html>
<html lang="vi">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SECURE ACCESS | CAMERA AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link
        href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap"
        rel="stylesheet">

    <link rel="stylesheet" href="/assets/css/variables.css">
    <link rel="stylesheet" href="/assets/css/main.css">

    <style>
        body {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background: #000 url('data:image/svg+xml;utf8,<svg width="40" height="40" xmlns="http://www.w3.org/2000/svg"><path d="M0 0h40v40H0z" fill="none"/><circle cx="20" cy="20" r="1" fill="%23333"/></svg>') repeat;
        }

        .login-box {
            width: 100%;
            max-width: 400px;
            background: var(--color-surface);
            border: 1px solid var(--color-border-bright);
            padding: 40px;
            position: relative;
            box-shadow: 0 0 50px rgba(0, 0, 0, 0.8);
        }

        .login-box::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--color-primary);
            box-shadow: 0 0 15px var(--color-primary);
        }

        .login-header {
            text-align: center;
            margin-bottom: 32px;
        }

        .login-logo {
            width: 48px;
            height: 48px;
            background: var(--color-primary);
            color: #fff;
            font-weight: 800;
            font-size: 1.2rem;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px;
            border-radius: 2px;
        }

        .g-input {
            width: 100%;
            background: #000;
            border: 1px solid var(--color-border);
            padding: 14px 16px;
            color: #fff;
            font-family: var(--font-mono);
            font-weight: 700;
            border-radius: 2px;
            margin-bottom: 16px;
        }

        .g-input:focus {
            border-color: var(--color-primary);
            outline: none;
        }

        .error-msg {
            color: var(--color-error);
            font-size: 0.75rem;
            font-family: var(--font-mono);
            font-weight: 700;
            margin-bottom: 16px;
            display: none;
            background: rgba(239, 68, 68, 0.1);
            padding: 8px 12px;
            border-left: 2px solid var(--color-error);
        }

        .spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 1s ease-in-out infinite;
            display: inline-block;
        }

        @keyframes spin {
            to {
                transform: rotate(360deg);
            }
        }
    </style>
</head>

<body>

    <div class="login-box">
        <div class="login-header">
            <div class="login-logo">C</div>
            <h1 class="uppercase bold" style="font-size: 1.2rem; letter-spacing: 0.1em;">CAMERA AI</h1>
            <p class="text-dim font-mono" style="font-size: 0.7rem;">RESTRICTED ACCESS ONLY</p>
        </div>

        <div id="login-error" class="error-msg"></div>

        <form id="login-form">
            <div>
                <label class="uppercase bold text-dim"
                    style="font-size: 0.65rem; display: block; margin-bottom: 6px;">Cấp bậc / Tài khoản</label>
                <input type="text" name="username" class="g-input" placeholder="ID.QUAN_TRI" required
                    autocomplete="username">
            </div>
            <div>
                <label class="uppercase bold text-dim"
                    style="font-size: 0.65rem; display: block; margin-bottom: 6px;">Mã định danh (Mật khẩu)</label>
                <input type="password" name="password" class="g-input" placeholder="********" required
                    autocomplete="current-password">
            </div>

            <button type="submit" id="btn-submit" class="btn btn--primary"
                style="width: 100%; margin-top: 16px; padding: 14px; font-size: 0.85rem;">
                ĐĂNG NHẬP HỆ THỐNG
            </button>
        </form>
    </div>

    <script type="module" src="/assets/js/pages/LoginController.js"></script>

</body>

</html>