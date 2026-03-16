import ApiBase from '../core/ApiBase.js';

/**
 * CameraService - Xử lý toàn bộ nghiệp vụ camera chuẩn OOP
 */
class CameraService extends ApiBase {
    constructor(baseUrl) {
        super(baseUrl);
    }

    /**
     * Lấy danh sách camera
     */
    list(options = {}) {
        return this.get('/api/cameras', options);
    }

    /**
     * Chi tiết một camera
     */
    getById(id, options = {}) {
        return this.get(`/api/cameras/${id}`, options);
    }

    /**
     * Dữ liệu AI Live View Overlay
     */
    getLiveView(id, options = {}) {
        return this.get(`/api/cameras/${id}/live-view`, options);
    }

    /**
     * URL SSE (Server-Sent Events) để lắng nghe overlay liên tục
     */
    getLiveViewSseUrl(id) {
        return `${this.baseUrl}/api/cameras/${id}/live-view/sse`;
    }

    /**
     * Cập nhật cấu hình camera
     */
    update(id, data, options = {}) {
        return this.put(`/api/cameras/${id}`, data, options);
    }

    /**
     * Điều khiển camera
     */
    reboot(id) {
        return this.post(`/api/cameras/${id}/reboot`, {});
    }

    factoryReset(id) {
        return this.post(`/api/cameras/${id}/factory-reset`, {});
    }

    startOTA(id, url) {
        return this.post(`/api/cameras/${id}/ota`, { url });
    }

    setTrafficLight(id, state) {
        return this.post(`/api/cameras/${id}/traffic-light`, { state });
    }

    /**
     * Stream Helpers
     */
    getStreamUrl(id, options = {}) {
        const useCacheBust = options.cacheBust !== false;
        const suffix = useCacheBust ? `?t=${Date.now()}` : '';
        return `${this.baseUrl}/api/cameras/${id}/stream${suffix}`;
    }

    getSnapshotUrl(id, options = {}) {
        const useCacheBust = options.cacheBust !== false;
        const suffix = useCacheBust ? `?t=${Date.now()}` : '';
        return `${this.baseUrl}/api/cameras/${id}/snapshot${suffix}`;
    }
}

// Singleton instance for global app use
const cameraService = new CameraService(window.APP_CONFIG?.API_URL || '');
export default cameraService;
export { CameraService };
