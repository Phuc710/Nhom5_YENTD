import ApiBase from '../core/ApiBase.js';

/**
 * ViolationService - Quản lý dữ liệu vi phạm chuẩn OOP
 */
class ViolationService extends ApiBase {
    constructor(baseUrl) {
        super(baseUrl);
    }

    /**
     * Lấy danh sách vi phạm (có filter)
     */
    list(params = {}, options = {}) {
        const query = new URLSearchParams(
            Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined)
        ).toString();
        return this.get(`/api/violations${query ? '?' + query : ''}`, options);
    }

    /**
     * Lấy vi phạm gần đây nhất
     */
    getRecent(limit = 10, options = {}) {
        return this.get(`/api/violations/recent?limit=${limit}`, options);
    }

    /**
     * Chi tiết vi phạm
     */
    getById(id, options = {}) {
        return this.get(`/api/violations/${id}`, options);
    }
}

const violationService = new ViolationService(window.APP_CONFIG?.API_URL || '');
export default violationService;
export { ViolationService };
