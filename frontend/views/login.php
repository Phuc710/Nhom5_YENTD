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
            background: var(--color-bg);
            background-image:
                radial-gradient(circle at 0% 0%, rgba(0, 255, 136, 0.05) 0%, transparent 50%),
                radial-gradient(circle at 100% 100%, rgba(112, 0, 255, 0.05) 0%, transparent 50%);
            overflow: hidden;
        }

        .login-box {
            width: 100%;
            max-width: 440px;
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: var(--glass-blur);
            border: 1px solid var(--color-border-bright);
            padding: 48px;
            border-radius: var(--radius-lg);
            position: relative;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
            animation: slideUp 0.6s cubic-bezier(0.19, 1, 0.22, 1);
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }

            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .login-header {
            text-align: center;
            margin-bottom: 40px;
        }

        .login-logo {
            width: 64px;
            height: 64px;
            background: var(--color-primary);
            color: #000;
            font-weight: 900;
            font-size: 1.8rem;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 20px;
            border-radius: 16px;
            box-shadow: 0 0 20px var(--color-primary-glow);
        }

        .g-input {
            width: 100%;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--color-border);
            padding: 16px 20px;
            color: #fff;
            font-family: var(--font-mono);
            font-weight: 700;
            font-size: 0.9rem;
            border-radius: var(--radius);
            margin-bottom: 20px;
            transition: all 0.3s;
        }

        .g-input:focus {
            border-color: var(--color-primary);
            background: rgba(0, 0, 0, 0.5);
            box-shadow: 0 0 15px rgba(0, 255, 136, 0.1);
            outline: none;
        }

        .input-label {
            font-size: 0.65rem;
            font-weight: 900;
            color: var(--color-text-dim);
            text-transform: uppercase;
            letter-spacing: 0.15em;
            display: block;
            margin-bottom: 8px;
        }

        .error-msg {
            color: #ff4444;
            font-size: 0.7rem;
            font-family: var(--font-mono);
            font-weight: 700;
            margin-bottom: 20px;
            display: none;
            background: rgba(255, 68, 68, 0.1);
            padding: 12px 16px;
            border-radius: var(--radius-sm);
            border: 1px solid rgba(255, 68, 68, 0.2);
            animation: shake 0.4s ease;
        }

        @keyframes shake {

            0%,
            100% {
                transform: translateX(0);
            }

            25% {
                transform: translateX(-5px);
            }

            75% {
                transform: translateX(5px);
            }
        }

        .btn-premium {
            width: 100%;
            background: var(--color-primary);
            color: #000;
            border: none;
            padding: 18px;
            font-weight: 900;
            font-size: 0.9rem;
            border-radius: var(--radius);
            cursor: pointer;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            transition: all 0.3s;
            box-shadow: 0 4px 15px var(--color-primary-glow);
        }

        .btn-premium:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px var(--color-primary-glow);
            filter: brightness(1.1);
        }

        .login-footer {
            margin-top: 32px;
            text-align: center;
            font-size: 0.6rem;
            color: var(--color-text-dim);
            text-transform: uppercase;
            letter-spacing: 0.2em;
        }
    </style>
</head>

<body>

    <div class="login-box">
        <div class="login-header">
            <div class="login-logo">A</div>
            <h1 class="bold uppercase" style="font-size: 1.5rem; letter-spacing: -0.01em; line-height: 1;">
                GIÁM SÁT <span class="text-primary">THÔNG MINH</span>
            </h1>
            <p class="text-dim uppercase bold mt-1" style="font-size: 0.65rem; letter-spacing: 0.1em;">
                Quản lý Hệ Thống Camera AI
            </p>
        </div>

        <div id="login-error" class="error-msg"></div>

        <form id="login-form">
            <div>
                <label class="input-label">Tên đăng nhập</label>
                <input type="text" name="username" class="g-input" placeholder="Nhập tài khoản" required
                    autocomplete="username">
            </div>
            <div>
                <label class="input-label">Mật khẩu</label>
                <input type="password" name="password" class="g-input" placeholder="Nhập mật khẩu" required
                    autocomplete="current-password">
            </div>

            <button type="submit" id="btn-submit" class="btn-premium">
                Đăng nhập hệ thống
            </button>
        </form>

        <div class="login-footer">
            Hệ thống giám sát an ninh • Kết nối bảo mật
        </div>
    </div>

    <script type="module" src="/assets/js/pages/LoginController.js"></script>

</body>

</html>