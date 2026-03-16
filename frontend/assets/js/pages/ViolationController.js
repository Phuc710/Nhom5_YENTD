import UIController from '../core/UIController.js';
import violationService from '../services/ViolationService.js';
import cameraService from '../services/CameraService.js';

/**
 * ViolationController - Quản lý trang nhật ký vi phạm CHUẨN OOP
 */
class ViolationController extends UIController {
    constructor() {
        super();
        this.page = 1;
        this.limit = 20;
        this.cameraId = '';
        this.licensePlate = '';
        this.dateRange = 'all';
        this.init();
    }

    async init() {
        console.log('📜 ViolationController Initializing...');
        await this.loadCameras();
        await this.search();
        this.setupListeners();
    }

    async loadCameras() {
        try {
            const cameras = await cameraService.list();
            const select = document.getElementById('filter-camera');
            if (select) {
                cameras.forEach(cam => {
                    const opt = document.createElement('option');
                    opt.value = cam.camera_id;
                    opt.textContent = cam.camera_name || `CAM-${cam.camera_id}`;
                    select.appendChild(opt);
                });
            }
        } catch (error) {
            console.error('Failed to load cameras for filter:', error);
        }
    }

    setupListeners() {
        const plateInput = document.getElementById('filter-plate');
        if (plateInput) {
            plateInput.addEventListener('input', (e) => {
                this.licensePlate = e.target.value.toUpperCase();
                this._debounceSearch();
            });
        }

        const cameraSelect = document.getElementById('filter-camera');
        if (cameraSelect) {
            cameraSelect.addEventListener('change', (e) => {
                this.cameraId = e.target.value;
                this.search();
            });
        }
    }

    _debounceSearch() {
        if (this.searchTimer) clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.search(), 500);
    }

    async search() {
        try {
            this.setHtml('violation-table-body', '<tr><td colspan="6" class="text-dim">Đang tìm kiếm...</td></tr>');
            const data = await violationService.list(this.buildQueryParams());
            this.renderTable(data);
        } catch (error) {
            this.showToast('Lỗi truy vấn dữ liệu', 'error');
        }
    }

    buildQueryParams() {
        const params = {
            page: this.page,
            limit: this.limit
        };

        if (this.cameraId) {
            params.camera_id = this.cameraId;
        }

        if (this.licensePlate) {
            params.license_plate = this.licensePlate;
        }

        const range = this.resolveDateRange(this.dateRange);
        if (range.date_from) {
            params.date_from = range.date_from;
        }
        if (range.date_to) {
            params.date_to = range.date_to;
        }

        return params;
    }

    resolveDateRange(range) {
        if (range === 'today') {
            const today = this.formatDate(new Date());
            return { date_from: today, date_to: today };
        }

        if (range === '7d') {
            const today = new Date();
            const from = new Date(today);
            from.setDate(from.getDate() - 6);
            return {
                date_from: this.formatDate(from),
                date_to: this.formatDate(today)
            };
        }

        return {};
    }

    formatDate(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    renderTable(violations) {
        const tbody = document.getElementById('violation-table-body');
        if (!tbody) return;

        if (violations.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-dim">Không tìm thấy bản ghi nào phù hợp.</td></tr>';
            return;
        }

        tbody.innerHTML = violations.map(v => `
            <tr onclick="location.href='/violation/${v.id}'" style="cursor:pointer">
                <td><img src="${v.cropped_plate_url || v.full_image_url}" style="width:60px; height:32px; object-fit:cover; border:1px solid var(--color-border);"></td>
                <td class="bold text-primary">${v.license_plate || '---'}</td>
                <td>${v.camera_name || v.camera_id}</td>
                <td class="text-dim">${new Date(v.timestamp).toLocaleString('vi-VN')}</td>
                <td><span class="badge ${v.confidence > 0.8 ? 'badge--online' : 'badge--offline'}">${(v.confidence * 100).toFixed(1)}%</span></td>
                <td style="text-align:right">
                    <a href="/violation/${v.id}" class="text-primary bold uppercase" style="font-size:0.7rem">Chi tiết</a>
                </td>
            </tr>
        `).join('');
    }

    setRange(range, btn) {
        this.dateRange = range;
        document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('btn--primary'));
        btn.classList.add('btn--primary');
        this.search();
    }
}

// Global exposure
window.ViolationController = ViolationController;

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new ViolationController();
});
