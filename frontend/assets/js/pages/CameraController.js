import UIController from '../core/UIController.js';
import cameraService from '../services/CameraService.js';
import realtimeService from '../services/RealtimeService.js';

/**
 * CameraController - Quan ly trang chi tiet thiet bi CHUAN OOP
 */
class CameraController extends UIController {
    constructor(cameraId) {
        super();
        this.cameraId = cameraId;
        this.cameraData = null;
        this.streamRetryDelay = 2000;
        this.streamErrorShown = false;
        this.streamConnected = false;
        this.refreshInterval = 5000;
        this.isSyncing = false;
        this.pendingSync = false;
        this.init();
    }

    async init() {
        console.log(`CameraController[${this.cameraId}] Initializing...`);
        this.setupStream();
        this.setupRealtime();
        await this.sync();
        this.setupSSE();
        setInterval(() => this.scheduleSync(), this.refreshInterval);
        window.addEventListener('beforeunload', () => this.dispose(), { once: true });
    }

    setupSSE() {
        if (this.sseEventSource) {
            this.sseEventSource.close();
        }
        const sseUrl = cameraService.getLiveViewSseUrl(this.cameraId);
        this.sseEventSource = new EventSource(sseUrl);

        this.sseEventSource.onmessage = (event) => {
            try {
                const overlayData = JSON.parse(event.data);
                this.renderOverlay(overlayData);
            } catch (error) {
                console.error('Loi parse SSE:', error);
            }
        };

        this.sseEventSource.onerror = (error) => {
            console.warn('SSE Overlay disconnected, reconnecting...', error);
        };
    }

    async sync() {
        if (this.isSyncing) {
            this.pendingSync = true;
            return;
        }

        this.isSyncing = true;
        try {
            this.cameraData = await cameraService.getById(this.cameraId);
            this.renderInfo();
            this.renderTelemetry();
        } catch (error) {
            console.error('Sync failed:', error);
            this.showToast('Loi dong bo thiet bi', 'error');
        } finally {
            this.isSyncing = false;
            if (this.pendingSync) {
                this.pendingSync = false;
                this.scheduleSync();
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

            if (event.type === 'message' && this.shouldSyncFromRealtime(event.data)) {
                this.scheduleSync(150);
            }
        });
    }

    updateRealtimeStatus(connected) {
        const container = document.getElementById('connection-status');
        if (!container) return;

        container.innerHTML = `
            <span class="status-dot ${connected ? 'status-dot--online' : 'status-dot--offline'}"></span>
            <span class="uppercase bold" style="font-size: 0.65rem;">${connected ? 'He thong truc tuyen' : 'Dang doi backend'}</span>
        `;
    }

    shouldSyncFromRealtime(message) {
        const resources = Array.isArray(message?.resources) ? message.resources : [];
        if (!(resources.includes('cameras') || resources.includes('summary'))) {
            return false;
        }

        const changedCameraId = Number(message?.payload?.camera_id);
        return !changedCameraId || changedCameraId === Number(this.cameraId);
    }

    scheduleSync(delay = 0) {
        clearTimeout(this.syncTimer);
        this.syncTimer = setTimeout(() => this.sync(), delay);
    }

    setupStream() {
        const img = document.getElementById('camera-stream');
        if (!img) return;

        img.onload = () => {
            this.streamErrorShown = false;
            this.streamConnected = true;
            clearTimeout(img._streamRetryTimer);
            this.updateStreamBadge(true);
        };

        img.onerror = () => {
            this.streamConnected = false;
            this.updateStreamBadge(false);
            if (!this.streamErrorShown) {
                this.showToast('Mat ket noi luong MJPEG, dang thu ket noi lai', 'warning');
                this.streamErrorShown = true;
            }
            this.scheduleStreamReconnect();
        };

        this.connectStream(true);
    }

    connectStream(forceReload = false) {
        const img = document.getElementById('camera-stream');
        if (!img) return;

        const nextUrl = cameraService.getStreamUrl(this.cameraId, { cacheBust: forceReload });
        if (!forceReload && img.src === nextUrl) {
            return;
        }
        img.src = nextUrl;
    }

    scheduleStreamReconnect() {
        const img = document.getElementById('camera-stream');
        if (!img) return;

        clearTimeout(img._streamRetryTimer);
        img._streamRetryTimer = setTimeout(() => {
            this.connectStream(true);
        }, this.streamRetryDelay);
    }

    updateStreamBadge(isLive) {
        const badge = document.getElementById('cam-status-badge');
        if (!badge) return;
        badge.innerHTML = `<span class="badge ${isLive ? 'badge--online' : 'badge--offline'}">${isLive ? 'STREAM OK' : 'STREAM OFFLINE'}</span>`;
    }

    renderInfo() {
        const cam = this.cameraData;
        this.setText('cam-name', cam.camera_name || `CAM-${cam.camera_id}`);
        this.setText('cam-id', String(cam.camera_id).padStart(4, '0'));
        this.setText('cam-mac', cam.mac_address);
        this.setText('cam-ip', cam.ip_address);
        this.setText('cam-fw', cam.fw_version);
        this.setText('cam-idf', cam.idf_version);
        this.setText('cam-loc', cam.location);

        const isLive = this.streamConnected || (cam.stream_connected ?? cam.stream_running ?? cam.online);
        this.updateStreamBadge(isLive);
    }

    renderTelemetry() {
        const cam = this.cameraData;

        const rssi = cam.wifi_rssi || 0;
        this.setText('tel-rssi', `${rssi} dBm`);

        const temp = cam.cpu_temp || 0;
        this.setText('tel-temp', `${temp.toFixed(1)} C`);

        const heap = cam.free_heap || 0;
        this.setText('tel-heap', `${(heap / 1024).toFixed(1)} KB`);

        this.updateStatusPill('pill-camera', cam.camera_ok);
        this.updateStatusPill('pill-mqtt', cam.mqtt_connected);
    }

    renderOverlay(overlay) {
        const wrapper = document.querySelector('.mjpeg-wrapper');
        const img = document.getElementById('camera-stream');
        if (!wrapper || !img || !img.complete) return;

        wrapper.querySelectorAll('.ai-bbox').forEach((el) => el.remove());

        if (overlay.captured_at) {
            const timeStr = new Date(overlay.captured_at).toLocaleTimeString('vi-VN', { hour12: false });
            this.setText('overlay-clock', `AI INFER: ${timeStr} | LATENCY: ${overlay.processing_ms}ms`);
        }

        if (!overlay.detections || overlay.detections.length === 0) return;

        const origW = overlay.frame_width || 640;
        const origH = overlay.frame_height || 480;

        overlay.detections.forEach((det) => {
            if (!det.bbox) return;
            const [x1, y1, x2, y2] = det.bbox;
            const leftPct = (x1 / origW) * 100;
            const topPct = (y1 / origH) * 100;
            const widthPct = ((x2 - x1) / origW) * 100;
            const heightPct = ((y2 - y1) / origH) * 100;

            const box = document.createElement('div');
            box.className = 'ai-bbox';
            box.style.left = `${leftPct}%`;
            box.style.top = `${topPct}%`;
            box.style.width = `${widthPct}%`;
            box.style.height = `${heightPct}%`;

            const boxColor = det.is_violation ? 'var(--color-error)' : 'var(--color-success)';
            box.style.borderColor = boxColor;

            const label = document.createElement('div');
            label.className = 'ai-bbox-label';
            label.style.backgroundColor = boxColor;
            label.textContent = `${det.plate_text || 'VEHICLE'} ${(det.confidence * 100).toFixed(0)}%`;
            box.appendChild(label);

            wrapper.appendChild(box);
        });
    }

    async reboot() {
        if (!confirm('Xac nhan khoi dong lai thiet bi?')) return;
        try {
            await cameraService.reboot(this.cameraId);
            this.showToast('Da gui lenh Reboot', 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    async factoryReset() {
        if (!confirm('Canh bao: toan bo cau hinh se bi xoa. Tiep tuc?')) return;
        try {
            await cameraService.factoryReset(this.cameraId);
            this.showToast('Da gui lenh Reset', 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    async startOTA() {
        const url = prompt('Nhap URL Firmware (.bin):');
        if (!url) return;
        try {
            await cameraService.startOTA(this.cameraId, url);
            this.showToast('Da gui lenh OTA', 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    async setLight(state) {
        try {
            await cameraService.setTrafficLight(this.cameraId, state);
            this.showToast(`Da chuyen sang ${state.toUpperCase()}`, 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    dispose() {
        const img = document.getElementById('camera-stream');
        if (img) {
            clearTimeout(img._streamRetryTimer);
            img.onload = null;
            img.onerror = null;
            img.src = '';
        }

        if (this.sseEventSource) {
            this.sseEventSource.close();
            this.sseEventSource = null;
        }

        if (this.unsubscribeRealtime) {
            this.unsubscribeRealtime();
            this.unsubscribeRealtime = null;
        }

        clearTimeout(this.syncTimer);
    }
}

window.CameraController = CameraController;

document.addEventListener('DOMContentLoaded', () => {
    const cameraId = window.APP_CONFIG?.CAMERA_ID;
    if (cameraId) {
        window.controller = new CameraController(cameraId);
    }
});
