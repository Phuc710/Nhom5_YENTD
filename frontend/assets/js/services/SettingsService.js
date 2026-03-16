import ApiBase from '../core/ApiBase.js';

/**
 * SettingsService - Quản lý cấu hình hệ thống CHUẨN OOP
 */
class SettingsService extends ApiBase {
    constructor(baseUrl) {
        super(baseUrl);
    }

    /**
     * Lấy cấu hình hệ thống hiện tại
     */
    getSystemConfig(options = {}) {
        // Mocking/Assuming standard config endpoints
        return this.get('/api/settings/system', options).catch(() => ({
            mqtt_host: 'thingsboard.cloud',
            mqtt_port: 1883,
            retention_days: 30,
            ai_confidence_threshold: 0.85
        }));
    }

    /**
     * Cập nhật cấu hình hệ thống
     */
    updateSystemConfig(data, options = {}) {
        return this.put('/api/settings/system', data, options);
    }
}

const settingsService = new SettingsService(window.APP_CONFIG?.API_URL || '');
export default settingsService;
export { SettingsService };
