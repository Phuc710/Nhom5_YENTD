import ApiBase from '../core/ApiBase.js';

/**
 * AuthService - Quản lý quá trình xác thực (Login/Logout) CHUẨN OOP
 */
class AuthService extends ApiBase {
    constructor(baseUrl) {
        super(baseUrl);
    }

    /**
     * Gửi yêu cầu đăng nhập
     * @param {string} username 
     * @param {string} password 
     */
    async login(username, password) {
        // Here we simulate the login API call that PHP would handle or a JWT endpoint
        // For the current Supabase/PHP structure, this will likely hit a PHP endpoint like /api/auth/login
        // Or directly submit a form if not fully decoupled. Let's assume a JSON endpoint.
        try {
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', password);
            // formData.append('action', 'login');

            const response = await fetch('/process-login', { // Or wherever the PHP auth handler is
                method: 'POST',
                body: formData
            });

            if (response.redirected) {
                // If PHP handled the session and redirects
                window.location.href = response.url;
                return { success: true };
            }

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || 'Đăng nhập thất bại');
            }

            return data;
        } catch (error) {
            // Throw so controller can handle
            throw error;
        }
    }

    /**
     * Gửi yêu cầu đăng xuất
     */
    async logout() {
        window.location.href = '/logout';
    }
}

const authService = new AuthService(window.APP_CONFIG?.API_URL || '');
export default authService;
export { AuthService };
