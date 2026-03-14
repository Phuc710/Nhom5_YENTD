<?php
namespace Frontend\App\Auth;

/**
 * Session.php - Secure session management.
 */
class Session
{
    public static function init(): void
    {
        if (session_status() !== PHP_SESSION_ACTIVE) {
            session_name('ytd_frontend');
            session_start();
        }
    }

    public static function set(string $key, mixed $value): void
    {
        $_SESSION[$key] = $value;
    }

    public static function get(string $key, mixed $default = null): mixed
    {
        return $_SESSION[$key] ?? $default;
    }

    public static function has(string $key): bool
    {
        return isset($_SESSION[$key]);
    }

    public static function remove(string $key): void
    {
        unset($_SESSION[$key]);
    }

    public static function destroy(): void
    {
        $_SESSION = [];
        if (ini_get("session.use_cookies")) {
            $params = session_get_cookie_params();
            setcookie(
                session_name(),
                '',
                time() - 42000,
                $params["path"],
                $params["domain"],
                $params["secure"],
                $params["httponly"]
            );
        }
        session_destroy();
    }

    public static function isLoggedIn(): bool
    {
        return self::has('user_id');
    }

    public static function requireLogin(): void
    {
        if (!self::isLoggedIn()) {
            header('Location: /login.php');
            exit;
        }
    }
}
