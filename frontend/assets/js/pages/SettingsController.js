import UIController from '../core/UIController.js';
import settingsService from '../services/SettingsService.js';

/**
 * SettingsController - Quản lý trang cấu hình CHUẨN OOP
 */
class SettingsController extends UIController {
    constructor() {
        super();
        this.form = document.getElementById('settings-form');
        this.btnSave = document.getElementById('btn-save-settings');
        this.init();
    }

    async init() {
        console.log('⚙️ SettingsController Initializing...');
        await this.loadConfig();
        this.setupListeners();
    }

    async loadConfig() {
        try {
            const config = await settingsService.getSystemConfig();
            this.hydrateForm(config);
        } catch (error) {
            this.showToast('Lỗi tải cấu hình hệ thống', 'error');
        }
    }

    hydrateForm(data) {
        if (!this.form) return;

        // Match form names to data keys
        Object.keys(data).forEach(key => {
            const input = this.form.elements[key];
            if (input) input.value = data[key];
        });
    }

    setupListeners() {
        if (this.form) {
            this.form.addEventListener('submit', (e) => this.handleSave(e));
        }
    }

    async handleSave(e) {
        e.preventDefault();

        const data = {};
        const formData = new FormData(this.form);
        formData.forEach((value, key) => data[key] = value);

        this.setSaving(true);

        try {
            await settingsService.updateSystemConfig(data);
            this.showToast('Đã lưu cấu hình hệ thống', 'success');
        } catch (error) {
            this.showToast(error.message || 'Lỗi lưu cấu hình', 'error');
        } finally {
            this.setSaving(false);
        }
    }

    setSaving(isSaving) {
        if (this.btnSave) {
            this.btnSave.disabled = isSaving;
            this.btnSave.innerHTML = isSaving ? '<div class="spinner text-primary"></div> ĐANG LƯU...' : 'LƯU CẤU HÌNH';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new SettingsController();
});
