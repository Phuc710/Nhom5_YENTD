import UIController from '../core/UIController.js';
import violationService from '../services/ViolationService.js';

/**
 * ViolationDetailController - Quản lý chi tiết vi phạm CHUẨN OOP
 */
class ViolationDetailController extends UIController {
    constructor(violationId) {
        super();
        this.violationId = violationId;
        this.data = null;
        this.init();
    }

    async init() {
        console.log(`🧐 ViolationDetailController[${this.violationId}] Initializing...`);
        await this.load();
    }

    async load() {
        try {
            const data = await violationService.getById(this.violationId);
            this.data = data;
            this.render();
        } catch (error) {
            this.showToast('Lỗi tải cấu hồ sơ vi phạm', 'error');
        }
    }

    render() {
        const v = this.data;
        if (!v) return;

        this.setText('v-id', `#${String(v.id).padStart(6, '0')}`);
        this.setText('v-id-head', String(v.id).padStart(6, '0'));
        this.setText('v-plate', v.license_plate || 'Chưa nhận diện được');
        this.setText('v-time', new Date(v.timestamp).toLocaleString('vi-VN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }));
        this.setText('v-camera', (v.camera_name || `UNIT-${v.camera_id}`));
        this.setText('v-location', (v.location || 'Chưa xác định vị trí'));
        this.setText('v-confidence', `${(v.confidence * 100).toFixed(1)}%`);
        this.setText('v-type', v.violation_type === 'red_light' ? 'Vượt đèn đỏ' : 'Vi phạm khác');

        // Images
        const fullImg = document.getElementById('v-full-image');
        if (fullImg) fullImg.src = v.full_image_url;

        const plateImg = document.getElementById('v-plate-image');
        if (plateImg) plateImg.src = v.cropped_plate_url || v.full_image_url;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const vId = window.APP_CONFIG?.VIOLATION_ID;
    if (vId) {
        window.controller = new ViolationDetailController(vId);
    }
});
