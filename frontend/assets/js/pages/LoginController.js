import UIController from '../core/UIController.js';
import authService from '../services/AuthService.js';

/**
 * LoginController - Quản lý trang đăng nhập CHUẨN OOP
 */
class LoginController extends UIController {
    constructor() {
        super();
        this.form = document.getElementById('login-form');
        this.btnSubmit = document.getElementById('btn-submit');
        this.init();
    }

    init() {
        if (this.form) {
            this.form.addEventListener('submit', (e) => this.handleLogin(e));
        }
    }

    async handleLogin(e) {
        e.preventDefault();

        const username = this.form.username.value.trim();
        const password = this.form.password.value;

        if (!username || !password) {
            this.showError('Yêu cầu nhập đầy đủ tài khoản & mật khẩu');
            return;
        }

        this.setLoading(true);

        try {
            const result = await authService.login(username, password);
            if (result.success) {
                window.location.href = '/';
            } else {
                this.showError(result.message || 'Đăng nhập thất bại');
                this.setLoading(false);
            }
        } catch (error) {
            this.showError(error.message);
            this.setLoading(false);
        }
    }

    showError(msg) {
        const errEl = document.getElementById('login-error');
        if (errEl) {
            errEl.textContent = `[ LỖI HỆ THỐNG: ${msg} ]`;
            errEl.style.display = 'block';
        }
    }

    setLoading(isLoading) {
        if (this.btnSubmit) {
            this.btnSubmit.disabled = isLoading;
            this.btnSubmit.innerHTML = isLoading ? '<div class="spinner"></div> ĐANG XÁC THỰC...' : 'ĐĂNG NHẬP HỆ THỐNG';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new LoginController();
});
