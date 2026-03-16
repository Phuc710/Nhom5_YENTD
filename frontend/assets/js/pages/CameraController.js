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
        this.setupTabs();
        this.setupStreamControls();
        this.setupSettingsHandlers();
        this.setupStream();
        this.setupRealtime();
        await this.sync();
        this.setupSSE();
        setInterval(() => this.scheduleSync(), this.refreshInterval);
        window.addEventListener('beforeunload', () => this.dispose(), { once: true });
    }

    setupTabs() {
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.onclick = () => {
                const tab = btn.dataset.tab;
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                document.getElementById(`tab-${tab}`).classList.add('active');

                if (tab === 'zones') this.initZoneDrawing();
            };
        });
    }

    setupStreamControls() {
        const toggle = document.getElementById('btn-stream-toggle');
        if (!toggle) return;
        toggle.onclick = () => {
            if (this.streamConnected) {
                this.disposeStream();
                toggle.textContent = 'Xem Live Stream';
                this.streamConnected = false;
            } else {
                this.connectStream(true);
                toggle.textContent = 'Dừng Live Stream';
            }
        };
    }

    setupSettingsHandlers() {
        const slider = document.getElementById('input-conf');
        const display = document.getElementById('val-conf');
        if (slider && display) {
            slider.oninput = () => {
                display.textContent = Number(slider.value).toFixed(2);
            };
        }

        const saveBtn = document.getElementById('btn-save-settings');
        if (saveBtn) {
            saveBtn.onclick = async () => {
                const conf = parseFloat(slider.value);
                const mode = document.getElementById('input-mode').value;
                const rotate180 = document.getElementById('check-rotate-180').checked;
                const flipHorizontal = document.getElementById('check-flip-horizontal').checked;

                try {
                    await cameraService.update(this.cameraId, {
                        confidence_threshold: conf,
                        operation_mode: mode,
                        rotate_180: rotate180,
                        flip_horizontal: flipHorizontal
                    });
                    this.showToast('Cập nhật thông số thành công', 'success');
                } catch (e) {
                    this.showToast('Không thể cập nhật cấu hình thiết bị', 'error');
                }
            };
        }
    }

    disposeStream() {
        const img = document.getElementById('camera-stream');
        if (img) {
            img.src = '';
            clearTimeout(img._streamRetryTimer);
        }
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
                console.error('Lỗi parse SSE:', error);
            }
        };

        this.sseEventSource.onerror = (error) => {
            console.warn('Mất kết nối Lớp phủ SSE, đang thử lại...', error);
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
            this.showToast('Lỗi đồng bộ thiết bị', 'error');
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
            <span class="uppercase bold" style="font-size: 0.65rem;">${connected ? 'Hệ thống trực tuyến' : 'Mất kết nối máy chủ...'}</span>
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
                this.showToast('Mất kết nối luồng MJPEG, đang thử kết nối lại', 'warning');
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
        badge.innerHTML = `<span class="badge ${isLive ? 'badge--online' : 'badge--offline'}">${isLive ? 'KẾT NỐI: OK' : 'MẤT KẾT NỐI'}</span>`;
    }

    renderInfo() {
        const cam = this.cameraData;
        this.setText('cam-name', cam.camera_name || `UNIT-${cam.camera_id}`);
        this.setText('cam-id', String(cam.camera_id).padStart(4, '0'));
        this.setText('cam-mac', cam.mac_address || 'Không xác định');
        this.setText('cam-ip', cam.ip_address || '0.0.0.0');
        this.setText('cam-loc', cam.location || 'Chưa xác định');

        // Update settings inputs from data
        const slider = document.getElementById('input-conf');
        if (slider) {
            slider.value = cam.confidence_threshold || 0.5;
            this.setText('val-conf', Number(slider.value).toFixed(2));
        }

        const modeSelect = document.getElementById('input-mode');
        if (modeSelect) modeSelect.value = cam.operation_mode || 'balanced';

        const rotateCheck = document.getElementById('check-rotate-180');
        if (rotateCheck) rotateCheck.checked = !!cam.rotate_180;

        const flipCheck = document.getElementById('check-flip-horizontal');
        if (flipCheck) flipCheck.checked = !!cam.flip_horizontal;

        const isLive = this.streamConnected || (cam.stream_connected ?? cam.stream_running ?? cam.online);
        this.updateStreamBadge(isLive);
    }

    renderTelemetry() {
        const cam = this.cameraData;

        const rssi = cam.wifi_rssi || 0;
        this.setText('tel-rssi', `${rssi} DB`);

        const temp = cam.cpu_temp || 0;
        this.setText('tel-temp', `${temp.toFixed(0)}°`);

        this.updateStatusPill('pill-camera', cam.camera_ok);
        this.updateStatusPill('pill-mqtt', cam.mqtt_connected);

        // Update pill text based on status
        this.setText('pill-camera-text', cam.camera_ok ? 'Cảm biến: OK' : 'Lỗi cảm biến');
        this.setText('pill-mqtt-text', cam.mqtt_connected ? 'Kết nối: OK' : 'Mất kết nối');
    }

    renderOverlay(overlay) {
        const wrapper = document.querySelector('.mjpeg-wrapper');
        const img = document.getElementById('camera-stream');
        if (!wrapper || !img || !img.complete) return;

        wrapper.querySelectorAll('.ai-bbox').forEach((el) => el.remove());

        if (overlay.captured_at) {
            const timeStr = new Date(overlay.captured_at).toLocaleTimeString('vi-VN', { hour12: false });
            this.setText('overlay-clock', `AI INFER: ${timeStr} | ĐỘ TRỄ: ${overlay.processing_ms}ms`);
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
            label.textContent = `${det.plate_text || 'XÁC MINH...'} ${(det.confidence * 100).toFixed(0)}%`;
            box.appendChild(label);

            wrapper.appendChild(box);
        });
    }

    async reboot() {
        if (!confirm('Xác nhận khởi động lại thiết bị?')) return;
        try {
            await cameraService.reboot(this.cameraId);
            this.showToast('Đã gửi lệnh Khởi động lại', 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    async factoryReset() {
        if (!confirm('Cảnh báo: toàn bộ cấu hình sẽ bị xóa. Tiếp tục?')) return;
        try {
            await cameraService.factoryReset(this.cameraId);
            this.showToast('Đã gửi lệnh Reset', 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    async startOTA() {
        const url = prompt('Nhập URL Firmware (.bin):');
        if (!url) return;
        try {
            await cameraService.startOTA(this.cameraId, url);
            this.showToast('Đã gửi lệnh OTA', 'success');
        } catch (error) {
            this.showToast(error.message, 'error');
        }
    }

    async setLight(state) {
        try {
            await cameraService.setTrafficLight(this.cameraId, state);
            this.showToast(`Đã chuyển sang ${state.toUpperCase()}`, 'success');
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

    initZoneDrawing() {
        if (this.zoneCanvasInitialized) return;

        const canvas = document.getElementById('zone-canvas');
        if (!canvas) return;

        this.ctx = canvas.getContext('2d');
        this.zones = [];
        this.activeTool = 'stop_line';
        this.isDrawing = false;
        this.startX = 0;
        this.startY = 0;
        this.currentBox = null;

        // Load existing zones
        this.loadZones();

        // Canvas events
        canvas.onmousedown = (e) => this.handleMouseDown(e);
        canvas.onmousemove = (e) => this.handleMouseMove(e);
        canvas.onmouseup = (e) => this.handleMouseUp(e);

        // Tool selection
        document.querySelectorAll('.canvas-toolbar [data-tool]').forEach(btn => {
            btn.onclick = () => {
                document.querySelectorAll('.canvas-toolbar [data-tool]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.activeTool = btn.dataset.tool;
            };
        });

        document.getElementById('btn-clear-zones').onclick = () => {
            if (confirm('Xóa toàn bộ các vùng đã vẽ?')) {
                this.zones = [];
                this.renderCanvas();
            }
        };

        document.getElementById('btn-save-zones').onclick = () => this.saveZones();

        this.zoneCanvasInitialized = true;
        this.renderCanvas();
    }

    async loadZones() {
        try {
            const zones = await cameraService.get(`/api/cameras/${this.cameraId}/zones`);
            this.zones = Array.isArray(zones) ? zones : [];
            this.renderCanvas();
        } catch (e) {
            console.warn('Failed to load zones', e);
        }
    }

    handleMouseDown(e) {
        const rect = e.target.getBoundingClientRect();
        this.startX = e.clientX - rect.left;
        this.startY = e.clientY - rect.top;
        this.isDrawing = true;
    }

    handleMouseMove(e) {
        if (!this.isDrawing) return;
        const rect = e.target.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        this.currentBox = {
            x: Math.min(this.startX, x),
            y: Math.min(this.startY, y),
            w: Math.abs(x - this.startX),
            h: Math.abs(y - this.startY)
        };
        this.renderCanvas();
    }

    handleMouseUp() {
        if (!this.isDrawing) return;
        this.isDrawing = false;
        if (this.currentBox && this.currentBox.w > 5 && this.currentBox.h > 5) {
            const toolNames = {
                stop_line: 'Vạch dừng',
                violation_zone: 'Vùng vi phạm',
                detection_zone: 'Vùng nhận diện'
            };
            this.zones.push({
                zone_type: this.activeTool,
                zone_name: `${toolNames[this.activeTool]}_${this.zones.length + 1}`,
                x: Math.round(this.currentBox.x),
                y: Math.round(this.currentBox.y),
                width: Math.round(this.currentBox.w),
                height: Math.round(this.currentBox.h),
                active: true
            });
        }
        this.currentBox = null;
        this.renderCanvas();
    }

    renderCanvas() {
        const canvas = document.getElementById('zone-canvas');
        if (!canvas || !this.ctx) return;

        // Resize canvas to match display size if needed
        if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
            canvas.width = canvas.clientWidth;
            canvas.height = canvas.clientHeight;
        }

        this.ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw existing zones
        this.zones.forEach(z => this.drawBox(z, false));

        // Draw current box
        if (this.currentBox) {
            this.drawBox({
                ...this.currentBox,
                width: this.currentBox.w,
                height: this.currentBox.h,
                zone_type: this.activeTool
            }, true);
        }
    }

    drawBox(z, isPreview) {
        const colors = {
            stop_line: '#00ff88',
            violation_zone: '#d4ff00',
            detection_zone: '#7000ff'
        };

        this.ctx.strokeStyle = colors[z.zone_type] || '#fff';
        this.ctx.lineWidth = 3;
        if (isPreview) this.ctx.setLineDash([8, 4]);
        else this.ctx.setLineDash([]);

        this.ctx.strokeRect(z.x, z.y, z.width, z.height);

        this.ctx.fillStyle = (colors[z.zone_type] || '#fff') + '11';
        this.ctx.fillRect(z.x, z.y, z.width, z.height);

        this.ctx.fillStyle = colors[z.zone_type] || '#fff';
        this.ctx.font = 'bold 11px JetBrains Mono';
        this.ctx.fillText(z.zone_name || z.zone_type, z.x + 6, z.y + 16);
    }

    async saveZones() {
        try {
            await cameraService.put(`/api/cameras/${this.cameraId}/zones`, {
                zones: this.zones
            });
            this.showToast('Đã lưu và triển khai vùng cấu hình', 'success');
        } catch (e) {
            this.showToast('Lỗi khi lưu vùng cấu hình', 'error');
        }
    }
}

window.CameraController = CameraController;

document.addEventListener('DOMContentLoaded', () => {
    const cameraId = window.APP_CONFIG?.CAMERA_ID;
    if (cameraId) {
        window.controller = new CameraController(cameraId);
    }
});
