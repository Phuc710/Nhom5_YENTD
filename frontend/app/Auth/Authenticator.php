<?php
namespace Frontend\App\Auth;

/**
 * Authenticator.php - Handles login and logout logic.
 */
class Authenticator
{
    /**
     * Authenticate user with predefined credentials (Police Department mock).
     * In a real app, this would query Supabase or a local DB.
     */
    public function login(string $username, string $password): bool
    {
        // Mock credentials for "Cục Cảnh Sát"
        $validUser = 'admin';
        $validPass = 'admin123'; // In production, use password_verify()

        if ($username === $validUser && $password === $validPass) {
            Session::set('user_id', 1);
            Session::set('username', $username);
            Session::set('role', 'Giám sát viên');
            Session::set('department', 'Cục Cảnh sát Giao thông');
            return true;
        }

        return false;
    }

    public function logout(): void
    {
        Session::destroy();
    }
}
