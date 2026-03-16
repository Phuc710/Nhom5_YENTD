import UIController from '../core/UIController.js';
import cameraService from '../services/CameraService.js';
import realtimeService from '../services/RealtimeService.js';
import violationService from '../services/ViolationService.js';

class DashboardController extends UIController {
    constructor() {
        super();
        this.cameras = [];
        this.violations = [];
        this.hasLoadedCameras = false;
        this.hasLoadedViolations = false;
        this.previewRetryDelay = 2000;
        this.refreshInterval = 5000;
        this.isRefreshing = false;
        this.pendingRefresh = false;
        this.renderedCameraKey = '';
        this.init();
    }

    async init() {
        console.log('DashboardController Initializing...');
        this.setupRealtime();
        await this.refresh();
        setInterval(() => this.scheduleRefresh(), this.refreshInterval);
    }

    async refresh() {
        if (this.isRefreshing) {
            this.pendingRefresh = true;
            return;
        }

        this.isRefreshing = true;
        try {
            const [cameraResult, violationResult] = await Promise.allSettled([
                cameraService.list(),
                violationService.getRecent(10)
            ]);

            if (cameraResult.status === 'fulfilled' && Array.isArray(cameraResult.value)) {
                this.cameras = cameraResult.value;
                this.hasLoadedCameras = true;
                this.renderSummary();
                this.renderCameras();
            } else if (cameraResult.status !== 'fulfilled' && !this.hasLoadedCameras) {
                this.renderErrorStates();
            }

            if (violationResult.status === 'fulfilled' && Array.isArray(violationResult.value)) {
                this.violations = violationResult.value;
                this.hasLoadedViolations = true;
                this.renderViolations();
            } else if (violationResult.status !== 'fulfilled' && !this.hasLoadedViolations) {
                const container = document.getElementById('recent-violations');
                if (container) {
                    container.innerHTML = '<div class="text-dim">Không thể tải danh sách vi phạm.</div>';
                }
            }

            if (cameraResult.status !== 'fulfilled' || violationResult.status !== 'fulfilled') {
                console.error('Dashboard sync degraded:', { cameraResult, violationResult });
            }
        } finally {
            this.isRefreshing = false;
            if (this.pendingRefresh) {
                this.pendingRefresh = false;
                this.scheduleRefresh();
            }
        }
    }

    setupRealtime() {
        realtimeService.connect();
        this.unsubscribeRealtime = realtimeService.subscribe((event) => {
            if (event.type === 'status') {
                this.updateRealtimeStatus(event.connected);
                return;
            }

            if (event.type === 'message' && this.shouldRefreshFromRealtime(event.data)) {
                this.scheduleRefresh(150);
            }
        });
    }

    updateRealtimeStatus(connected) {
        const container = document.getElementById('connection-status');
        if (!container) return;

        container.innerHTML = `
            <span class="status-dot ${connected ? 'status-dot--online' : 'status-dot--offline'}"></span>
            <span class="uppercase bold" style="font-size: 0.65rem;">${connected ? 'Hệ thống trực tuyến' : 'Mất kết nối máy chủ...'}</span>
        `;
    }

    shouldRefreshFromRealtime(message) {
        const resources = Array.isArray(message?.resources) ? message.resources : [];
        return resources.includes('cameras') || resources.includes('summary') || resources.includes('violations');
    }

    scheduleRefresh(delay = 0) {
        clearTimeout(this.refreshTimer);
        this.refreshTimer = setTimeout(() => this.refresh(), delay);
    }

    renderErrorStates() {
        const camContainer = document.getElementById('camera-grid');
        const vioContainer = document.getElementById('recent-violations');

        const errorHtml = `
            <div class="loading-state" style="grid-column: 1/-1; padding: 40px; text-align: center; border: 1px dashed var(--color-border);">
                <div class="text-error bold mb-1">KHÔNG THỂ KẾT NỐI MÁY CHỦ</div>
                <div class="text-dim uppercase" style="font-size: 0.7rem;">Dịch vụ ${window.APP_CONFIG?.API_URL} không phản hồi</div>
                <div class="text-dim mt-1" style="font-size: 0.75rem;">Vui lòng kiểm tra lại đường truyền mạng</div>
            </div>
        `;

        if (camContainer) camContainer.innerHTML = errorHtml;
        if (vioContainer) vioContainer.innerHTML = errorHtml;

        this.setText('stat-total-cam', '--');
        this.setText('stat-online-cam', '--');
        this.setText('stat-offline-cam', '--');
    }

    renderSummary() {
        if (!this.hasLoadedCameras) {
            this.setText('stat-total-cam', '--');
            this.setText('stat-online-cam', '--');
            this.setText('stat-offline-cam', '--');
            return;
        }

        const total = this.cameras.length;
        const online = this.cameras.filter((c) => (c.stream_connected ?? c.stream_running ?? c.online)).length;

        this.setText('stat-total-cam', total);
        this.setText('stat-online-cam', online);
        this.setText('stat-offline-cam', total - online);
    }

    renderCameras() {
        const container = document.getElementById('camera-grid');
        if (!container) return;

        if (!this.hasLoadedCameras) {
            container.innerHTML = '<div class="text-dim">Không thể tải danh sách camera.</div>';
            return;
        }

        if (this.cameras.length === 0) {
            this.cleanupPreviewHandlers(container);
            this.renderedCameraKey = '';
            container.innerHTML = '<div class="text-dim">Chưa có thiết bị nào được kết nối.</div>';
            return;
        }

        const nextKey = this.cameras.map((cam) => String(cam.camera_id)).join(',');
        if (this.renderedCameraKey !== nextKey) {
            this.cleanupPreviewHandlers(container);
            container.innerHTML = this.cameras.map((cam) => this._cameraCardTemplate(cam)).join('');
            this.attachPreviewHandlers(container);
            this.renderedCameraKey = nextKey;
        }

        this.updateCameraCardStates(container, this.cameras);
    }

    renderViolations() {
        const container = document.getElementById('recent-violations');
        if (!container) return;

        if (!this.hasLoadedViolations) {
            container.innerHTML = '<div class="text-dim">Khong tai duoc danh sach vi pham.</div>';
            return;
        }

        if (this.violations.length === 0) {
            container.innerHTML = '<div class="text-dim">Không có bản ghi vi phạm.</div>';
            return;
        }

        container.innerHTML = this.violations.map((v) => this._violationItemTemplate(v)).join('');
    }

    _cameraCardTemplate(cam) {
        const isLive = cam.stream_connected ?? cam.stream_running ?? cam.online;
        const statusText = isLive ? 'HOẠT ĐỘNG' : 'MẤT TÍN HIỆU';
        const statusClass = isLive ? 'badge--online' : 'badge--offline';

        return `
            <div class="g-card cam-card" onclick="location.href='/camera/${cam.camera_id}'">
                <div class="cam-card__media">
                    <img
                        src="${cameraService.getStreamUrl(cam.camera_id)}"
                        alt="Preview"
                        data-preview-camera-id="${cam.camera_id}"
                        style="display: ${isLive ? 'block' : 'none'};"
                    >
                    <div class="no-preview" data-preview-empty="${cam.camera_id}" style="display: ${isLive ? 'none' : 'flex'};">MẤT KẾT NỐI</div>
                    <div class="cam-card__badge-v2" data-preview-badge="${cam.camera_id}">
                        <span class="badge ${statusClass}">${isLive ? 'ĐANG HOẠT ĐỘNG' : 'MẤT KẾT NỐI'}</span>
                    </div>
                </div>
                <div class="g-card__body">
                    <div class="flex-between">
                        <div class="g-card__title">${cam.camera_name || `UNIT-${cam.camera_id}`}</div>
                        <div class="font-mono text-dim" style="font-size: 0.6rem;">#${String(cam.camera_id).padStart(4, '0')}</div>
                    </div>
                    
                    <div class="cam-meta-grid">
                        <div class="meta-item">
                            <span class="meta-label">Node IP</span>
                            <span class="meta-value font-mono">${cam.ip_address || '---'}</span>
                        </div>
                        <div class="meta-item">
                            <span class="meta-label">MAC Phần Cứng</span>
                            <span class="meta-value font-mono">${cam.mac_address || '---'}</span>
                        </div>
                    </div>

                    <div class="text-primary uppercase bold mt-1" style="font-size:0.55rem; letter-spacing: 0.1em;">
                        <i class="location-icon"></i> ${cam.location || 'Chưa xác định vị trí'}
                    </div>
                </div>
            </div>
        `;
    }

    attachPreviewHandlers(container) {
        container.querySelectorAll('[data-preview-camera-id]').forEach((img) => {
            if (img.dataset.previewBound === '1') {
                return;
            }

            img.dataset.previewBound = '1';
            const cameraId = img.dataset.previewCameraId;
            const badge = container.querySelector(`[data-preview-badge="${cameraId}"]`);
            const empty = container.querySelector(`[data-preview-empty="${cameraId}"]`);

            const setState = (isLive) => {
                const statusText = isLive ? 'ĐANG HOẠT ĐỘNG' : 'MẤT KẾT NỐI';
                const statusClass = isLive ? 'badge--online' : 'badge--offline';

                if (badge) {
                    badge.innerHTML = `<span class="badge ${statusClass}">${statusText}</span>`;
                }
                if (empty) {
                    empty.style.display = isLive ? 'none' : 'flex';
                }
                img.style.display = isLive ? 'block' : 'none';
            };

            const retry = () => {
                clearTimeout(img._previewRetryTimer);
                img._previewRetryTimer = setTimeout(() => {
                    img.src = cameraService.getStreamUrl(cameraId);
                }, this.previewRetryDelay);
            };

            img.onload = () => {
                clearTimeout(img._previewRetryTimer);
                setState(true);
            };

            img.onerror = () => {
                setState(false);
                retry();
            };
        });
    }

    updateCameraCardStates(container, cameras) {
        cameras.forEach((cam) => {
            const cameraId = String(cam.camera_id);
            const img = container.querySelector(`[data-preview-camera-id="${cameraId}"]`);
            const badge = container.querySelector(`[data-preview-badge="${cameraId}"]`);
            const empty = container.querySelector(`[data-preview-empty="${cameraId}"]`);
            if (!img || !badge || !empty) {
                return;
            }

            const isLive = cam.stream_connected ?? cam.stream_running ?? cam.online;
            const statusText = isLive ? 'ĐANG HOẠT ĐỘNG' : 'MẤT KẾT NỐI';
            const statusClass = isLive ? 'badge--online' : 'badge--offline';

            badge.innerHTML = `<span class="badge ${statusClass}">${statusText}</span>`;

            if (!isLive && !img._previewRetryTimer) {
                empty.style.display = 'flex';
            }
        });
    }

    cleanupPreviewHandlers(container) {
        container.querySelectorAll('[data-preview-camera-id]').forEach((img) => {
            clearTimeout(img._previewRetryTimer);
            img.onload = null;
            img.onerror = null;
        });
    }

    _violationItemTemplate(v) {
        return `
            <div class="violation-item" onclick="location.href='/violation/${v.id}'">
                <div class="violation-item__accent"></div>
                <div style="flex:1">
                    <div class="bold font-mono text-primary">${v.license_plate || 'KHÔNG BIỂN'}</div>
                    <div class="text-dim" style="font-size:0.75rem">${v.camera_name} - ${new Date(v.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="badge badge--online">${v.confidence ? (v.confidence * 100).toFixed(0) : 0}%</div>
            </div>
        `;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new DashboardController();
});
