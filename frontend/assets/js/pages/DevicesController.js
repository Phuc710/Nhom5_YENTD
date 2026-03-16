import UIController from '../core/UIController.js';
import cameraService from '../services/CameraService.js';
import realtimeService from '../services/RealtimeService.js';

class DevicesController extends UIController {
    constructor() {
        super();
        this.cameras = [];
        this.previewRetryDelay = 2000;
        this.filter = {
            keyword: '',
            status: '',
        };
        this.isRefreshing = false;
        this.pendingRefresh = false;
        this.renderedCameraKey = '';
        this.init();
    }

    async init() {
        console.log('DevicesController Initializing...');
        this.setupRealtime();
        await this.refresh();
        this.setupListeners();
        setInterval(() => this.scheduleRefresh(), 5000);
    }

    setupListeners() {
        const searchInput = document.getElementById('device-search');
        if (searchInput) {
            searchInput.addEventListener('input', (event) => {
                this.filter.keyword = event.target.value.toLowerCase();
                this.applyFilter();
            });
        }

        const statusSelect = document.getElementById('device-status');
        if (statusSelect) {
            statusSelect.addEventListener('change', (event) => {
                this.filter.status = event.target.value;
                this.applyFilter();
            });
        }
    }

    async refresh() {
        if (this.isRefreshing) {
            this.pendingRefresh = true;
            return;
        }

        this.isRefreshing = true;
        try {
            this.cameras = await cameraService.list();
            this.applyFilter();
        } catch (error) {
            console.error('Devices refresh failed:', error);
            this.showToast('Không thể tải danh sách thiết bị', 'error');
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
            <span class="uppercase bold" style="font-size: 0.65rem;">${connected ? 'Hệ thống trực tuyến' : 'Mất kết nối máy chủ'}</span>
        `;
    }

    shouldRefreshFromRealtime(message) {
        const resources = Array.isArray(message?.resources) ? message.resources : [];
        return resources.includes('cameras') || resources.includes('summary');
    }

    scheduleRefresh(delay = 0) {
        clearTimeout(this.refreshTimer);
        this.refreshTimer = setTimeout(() => this.refresh(), delay);
    }

    applyFilter() {
        const filtered = this.cameras.filter((cam) => {
            const isLive = cam.stream_connected ?? cam.stream_running ?? cam.online;
            const matchesKeyword = !this.filter.keyword
                || `${cam.camera_name} ${cam.location}`.toLowerCase().includes(this.filter.keyword);
            const matchesStatus = !this.filter.status
                || (this.filter.status === 'online' ? isLive : !isLive);
            return matchesKeyword && matchesStatus;
        });

        this.renderGrid(filtered);
    }

    renderGrid(cameras) {
        const container = document.getElementById('device-grid');
        if (!container) return;

        if (cameras.length === 0) {
            this.cleanupPreviewHandlers(container);
            this.renderedCameraKey = '';
            container.innerHTML = '<div class="text-dim uppercase bold" style="padding: 64px; text-align: center;">Không tìm thấy thiết bị phù hợp.</div>';
            return;
        }

        const nextKey = cameras.map((cam) => String(cam.camera_id)).join(',');
        if (this.renderedCameraKey !== nextKey) {
            this.cleanupPreviewHandlers(container);
            container.innerHTML = cameras.map((cam) => this._deviceCardTemplate(cam)).join('');
            this.attachPreviewHandlers(container);
            this.renderedCameraKey = nextKey;
        }

        this.updateCardStates(container, cameras);
    }

    _deviceCardTemplate(cam) {
        const isLive = cam.stream_connected ?? cam.stream_running ?? cam.online;
        return `
            <div class="g-card cam-card" onclick="location.href='/camera/${cam.camera_id}'">
                <div class="cam-card__media">
                    <img
                        src="${cameraService.getStreamUrl(cam.camera_id)}"
                        alt="Preview"
                        data-preview-camera-id="${cam.camera_id}"
                    >
                    <div class="no-preview" data-preview-empty="${cam.camera_id}" style="display:none;">MẤT KẾT NỐI</div>
                    <div class="cam-card__status-bar" data-preview-badge="${cam.camera_id}">
                        <span class="status-dot ${isLive ? 'status-dot--online' : 'status-dot--offline'}"></span>
                        <span class="uppercase bold" style="font-size:0.6rem;">${isLive ? 'Đang hoạt động' : 'Mất kết nối'}</span>
                    </div>
                </div>
                <div class="g-card__body">
                    <div class="flex-between mb-1">
                        <div class="g-card__title" style="font-size: 0.95rem;">${cam.camera_name || `UNIT-${cam.camera_id}`}</div>
                    </div>
                    <div class="text-dim uppercase bold" style="font-size: 0.65rem; margin-bottom: 12px;">${cam.location || 'Chưa cấu hình vị trí'}</div>
                    <div class="device-stats flex-between">
                        <div class="stat-item">
                            <div class="text-dim uppercase" style="font-size: 0.55rem;">ID</div>
                            <div class="font-mono" style="font-size: 0.8rem;">#${String(cam.camera_id).padStart(3, '0')}</div>
                        </div>
                        <div class="stat-item" style="text-align: right;">
                            <div class="text-dim uppercase" style="font-size: 0.55rem;">Vi phạm</div>
                            <div class="font-mono text-primary" style="font-size: 0.8rem;">${cam.violations_today || 0}</div>
                        </div>
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
                if (badge) {
                    badge.innerHTML = `
                        <span class="status-dot ${isLive ? 'status-dot--online' : 'status-dot--offline'}"></span>
                        <span class="uppercase bold" style="font-size:0.6rem;">${isLive ? 'Đang hoạt động' : 'Mất kết nối'}</span>
                    `;
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

    updateCardStates(container, cameras) {
        cameras.forEach((cam) => {
            const cameraId = String(cam.camera_id);
            const badge = container.querySelector(`[data-preview-badge="${cameraId}"]`);
            if (!badge) {
                return;
            }

            const isLive = cam.stream_connected ?? cam.stream_running ?? cam.online;
            badge.innerHTML = `
                <span class="status-dot ${isLive ? 'status-dot--online' : 'status-dot--offline'}"></span>
                <span class="uppercase bold" style="font-size:0.6rem;">${isLive ? 'Đang hoạt động' : 'Mất kết nối'}</span>
            `;
        });
    }

    cleanupPreviewHandlers(container) {
        container.querySelectorAll('[data-preview-camera-id]').forEach((img) => {
            clearTimeout(img._previewRetryTimer);
            img.onload = null;
            img.onerror = null;
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.controller = new DevicesController();
});
