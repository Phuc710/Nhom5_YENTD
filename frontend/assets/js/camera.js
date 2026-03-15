let currentCamera = null;
let streamConnected = false;
let zoneEditor = null;
const CAMERA_ID = window.APP_CONFIG?.CAMERA_ID;

document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    bindActionUI();
    bindZoneUI();

    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: `camera-detail-${CAMERA_ID}`,
            resources: ['cameras'],
            intervalVisible: 12_000,
            intervalHidden: 60_000,
            run: () => api.getCamera(CAMERA_ID, { requestKey: `camera-detail-${CAMERA_ID}` }),
            onData: (camera) => {
                currentCamera = camera;
                renderCameraInfo(camera);
                syncSettingsForm(camera);
            },
        });

        window.liveDataHub.register({
            id: `camera-live-${CAMERA_ID}`,
            resources: ['stream'],
            intervalVisible: 2_000,
            intervalHidden: 10_000,
            run: () => api.previewCameraLive(CAMERA_ID, { requestKey: `camera-live-${CAMERA_ID}` }),
            onData: renderLiveView,
            onError: renderLiveViewError,
        });

        window.liveDataHub.register({
            id: `camera-violations-${CAMERA_ID}`,
            resources: ['violations'],
            intervalVisible: 10_000,
            intervalHidden: 60_000,
            run: () => api.getViolations({ camera_id: CAMERA_ID, limit: 10 }, { requestKey: `camera-violations-${CAMERA_ID}` }),
            onData: renderCameraViolations,
            onError: renderCameraViolationError,
        });

        window.liveDataHub.register({
            id: `camera-zones-${CAMERA_ID}`,
            resources: ['zones'],
            intervalVisible: 20_000,
            intervalHidden: 120_000,
            run: () => api.getZones(CAMERA_ID, { requestKey: `camera-zones-${CAMERA_ID}` }),
            onData: renderZones,
            onError: renderZoneError,
        });
        return;
    }

    refreshFallback();
    setInterval(refreshFallback, 5000);
});

async function refreshFallback() {
    try {
        const [camera, live, violations] = await Promise.all([
            api.getCamera(CAMERA_ID),
            api.previewCameraLive(CAMERA_ID),
            api.getViolations({ camera_id: CAMERA_ID, limit: 10 }),
        ]);
        currentCamera = camera;
        renderCameraInfo(camera);
        syncSettingsForm(camera);
        renderLiveView(live);
        renderCameraViolations(violations);
        renderZones(await api.getZones(CAMERA_ID));
    } catch (error) {
        console.error('Fallback refresh failed', error);
    }
}

function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    tabBtns.forEach((btn) => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            tabBtns.forEach((item) => item.classList.remove('active'));
            tabContents.forEach((item) => item.classList.add('hidden'));
            btn.classList.add('active');
            const target = document.getElementById(`tab${tabId.charAt(0).toUpperCase()}${tabId.slice(1)}`);
            if (target) target.classList.remove('hidden');
        });
    });
}



function bindZoneUI() {
    const reloadBtn = document.getElementById('btnReloadZones');
    const clearBtn = document.getElementById('btnClearZones');
    const saveBtn = document.getElementById('btnSaveZones');
    const typeSelect = document.getElementById('zoneTypeSelect');
    const zoneImg = document.getElementById('zoneEditorImg');
    const zoneWrap = zoneImg?.parentElement;
    if (!zoneImg || !zoneWrap || typeof ZoneEditor === 'undefined') return;

    zoneImg.src = api.getCameraSnapshotProxyUrl(CAMERA_ID, Date.now());
    zoneEditor = new ZoneEditor(zoneWrap, zoneImg);
    zoneEditor.setZoneType(typeSelect?.value || 'detection');
    zoneEditor.on('change', (zones) => {
        setText('zoneStatus', `${zones.length} vùng chưa lưu`);
    });

    typeSelect?.addEventListener('change', () => zoneEditor?.setZoneType(typeSelect.value));
    reloadBtn?.addEventListener('click', async () => {
        zoneImg.src = api.getCameraSnapshotProxyUrl(CAMERA_ID, Date.now());
        try {
            renderZones(await api.getZones(CAMERA_ID));
        } catch (error) {
            renderZoneError(error);
        }
    });
    clearBtn?.addEventListener('click', () => {
        zoneEditor?.clearAll();
        setText('zoneStatus', 'Đã xóa vùng tạm thời, chưa lưu');
    });
    saveBtn?.addEventListener('click', saveZones);
}

function bindActionUI() {
    const rebootBtn = document.getElementById('btnReboot');
    rebootBtn?.addEventListener('click', rebootCamera);
}

function renderCameraInfo(camera) {
    setText('camStatus', camera.online ? 'Online' : 'Offline');
    setText('camIp', camera.ip_address || '--');
    setText('camMac', camera.mac_address || '--');
    setText('camFw', camera.fw_version || '--');

    if (camera.stream_url && !streamConnected) {
        connectStream();
    }
}

function syncSettingsForm(camera) {
    const nameInput = document.getElementById('cfgName');
    const locInput = document.getElementById('cfgLocation');
    if (nameInput && !nameInput.matches(':focus')) nameInput.value = camera.camera_name || '';
    if (locInput && !locInput.matches(':focus')) locInput.value = camera.location || '';
}

function connectStream() {
    const img = document.getElementById('streamImg');
    if (!img) return;
    streamConnected = true;
    img.src = api.getCameraStreamProxyUrl(CAMERA_ID, Date.now());
    setText('streamInfo', 'Đang truyền MJPEG trực tiếp từ camera qua Backend');
    img.addEventListener('load', () => renderStreamBoxes(null), { once: false });
}

function renderLiveView(payload) {
    if (!payload) return;
    const overlay = payload.overlay || {};
    const detections = overlay.detections || [];

    const state = (overlay.traffic_light_state || 'none').toLowerCase();
    const dots = {
        red: document.getElementById('dotRed'),
        yellow: document.getElementById('dotYellow'),
        green: document.getElementById('dotGreen'),
    };
    if (dots.red) dots.red.classList.toggle('active', state === 'red');
    if (dots.yellow) dots.yellow.classList.toggle('active', state === 'yellow');
    if (dots.green) dots.green.classList.toggle('active', state === 'green');

    setText('overlayFps', overlay.processing_ms ? `${overlay.processing_ms} ms` : '-- ms');
    renderStreamBoxes(overlay);
}

function renderLiveViewError(error) {
    setText('streamInfo', `Lỗi preview: ${error.message}`);
    renderStreamBoxes(null);
}

function renderStreamBoxes(overlay) {
    const layer = document.getElementById('streamBboxLayer');
    const img = document.getElementById('streamImg');
    if (!layer || !img) return;

    layer.innerHTML = '';

    const detections = overlay?.detections || [];
    const frameWidth = overlay?.frame_width;
    const frameHeight = overlay?.frame_height;
    if (!detections.length || !frameWidth || !frameHeight) return;

    const containerWidth = img.clientWidth;
    const containerHeight = img.clientHeight;
    if (!containerWidth || !containerHeight) return;

    const frameRatio = frameWidth / frameHeight;
    const containerRatio = containerWidth / containerHeight;
    let renderedWidth = containerWidth;
    let renderedHeight = containerHeight;
    let offsetX = 0;
    let offsetY = 0;

    if (containerRatio > frameRatio) {
        renderedWidth = containerHeight * frameRatio;
        offsetX = (containerWidth - renderedWidth) / 2;
    } else {
        renderedHeight = containerWidth / frameRatio;
        offsetY = (containerHeight - renderedHeight) / 2;
    }

    detections.forEach((item) => {
        const bbox = item.bbox;
        if (!bbox) return;
        const box = document.createElement('div');
        box.className = `stream-bbox${item.is_violation ? ' stream-bbox--violation' : item.crossed_stop_line ? ' stream-bbox--warning' : ''}`;
        box.style.left = `${offsetX + (bbox.x1 / frameWidth) * renderedWidth}px`;
        box.style.top = `${offsetY + (bbox.y1 / frameHeight) * renderedHeight}px`;
        box.style.width = `${((bbox.x2 - bbox.x1) / frameWidth) * renderedWidth}px`;
        box.style.height = `${((bbox.y2 - bbox.y1) / frameHeight) * renderedHeight}px`;

        const label = document.createElement('div');
        label.className = 'stream-bbox__label';
        const zoneText = item.matched_zones?.length ? ` | ${item.matched_zones.join(', ')}` : '';
        const stopText = item.matched_stop_lines?.length ? ` | vạch dừng:${item.matched_stop_lines.join(', ')}` : '';
        const vioText = item.is_violation ? ' | VI PHẠM' : item.crossed_stop_line ? ' | chạm vạch' : '';
        label.textContent = `${item.plate_text || 'Không rõ'} | ${((item.confidence || 0) * 100).toFixed(1)}%${zoneText}${stopText}${vioText}`;
        box.appendChild(label);
        layer.appendChild(box);
    });
}

function renderZones(zones) {
    if (!zoneEditor) return;
    zoneEditor.loadZones(zones || []);

    const count = (zones || []).length;
    let statusText = `${count} vùng đang hoạt động`;
    if (count > 0) {
        const types = [...new Set(zones.map(z => z.zone_type))];
        statusText += ` (${types.join(', ')})`;
    }
    setText('zoneStatus', statusText);
}

function renderZoneError(error) {
    setText('zoneStatus', `Loi zone: ${error.message}`);
}

function renderCameraViolations(violations) {
    const tbody = document.getElementById('recentList');
    if (!tbody) return;
    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px;" class="text-muted">Chưa có vi phạm nào.</td></tr>';
        return;
    }

    tbody.innerHTML = violations.map((item) => `
        <tr>
            <td><img src="${item.cropped_plate_url || item.full_image_url}" style="width:60px; height:36px; border-radius:2px; object-fit:cover;"></td>
            <td><span class="badge" style="background:#222; border:1px solid #333; color:#fff; font-family:monospace; font-size:1rem;">${item.license_plate || '---'}</span></td>
            <td style="font-size:0.8rem; color:var(--color-text-dim)">${formatDateVN(item.timestamp)}</td>
            <td style="font-weight:700; color:var(--color-primary)">${item.confidence ? `${(item.confidence * 100).toFixed(1)}%` : '--'}</td>
            <td><a href="/violation-detail?id=${item.id}" class="btn btn--outline" style="padding:4px 8px; font-size:0.75rem;">Chi tiết</a></td>
        </tr>
    `).join('');
}

function renderCameraViolationError(error) {
    const tbody = document.getElementById('recentList');
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="color:var(--color-error); text-align:center;">Lỗi: ${error.message}</td></tr>`;
}



async function setLight(state) {
    try {
        await api.setTrafficLightState?.(CAMERA_ID, state);
        window.ui?.toast(`Đã đổi sang: ${state.toUpperCase()}`, 'success');
    } catch (error) {
        window.ui?.toast(`Lỗi điều khiển: ${error.message}`, 'error');
    }
}

async function saveSettings() {
    const payload = {
        camera_name: document.getElementById('cfgName').value.trim(),
        location: document.getElementById('cfgLocation').value.trim(),
    };
    try {
        await api.updateCamera(CAMERA_ID, payload);
        window.ui?.toast('Đã lưu cấu hình', 'success');
    } catch (error) {
        window.ui?.toast(`Lỗi lưu: ${error.message}`, 'error');
    }
}

async function saveZones() {
    if (!zoneEditor) return;
    const zones = zoneEditor.getZones();
    setText('zoneStatus', 'Đang lưu zones...');
    try {
        const saved = await api.saveZones(CAMERA_ID, zones, { requestKey: `save-zones-${CAMERA_ID}` });
        renderZones(saved);
        window.ui?.toast('Đã lưu zones thành công', 'success');
    } catch (error) {
        setText('zoneStatus', `Lỗi lưu zone: ${error.message}`);
        window.ui?.toast(`Lỗi zone: ${error.message}`, 'error');
    }
}

async function factoryReset() {
    if (!confirm('Xác nhận khôi phục cài đặt gốc camera này?')) return;
    try {
        await api.factoryResetCamera(CAMERA_ID);
        window.ui?.toast('Đã gửi lệnh reset', 'success');
    } catch (error) {
        window.ui?.toast(`Lỗi: ${error.message}`, 'error');
    }
}

async function rebootCamera() {
    if (!confirm('Khởi động lại camera này?')) return;
    try {
        await api.rebootCamera(CAMERA_ID);
        window.ui?.toast('Đã gửi lệnh khởi động lại', 'success');
    } catch (error) {
        window.ui?.toast(`Lỗi reboot: ${error.message}`, 'error');
    }
}

async function startOTA() {
    const url = document.getElementById('cfgOtaUrl')?.value.trim();
    if (!url) {
        window.ui?.toast('Hay nhap URL firmware', 'warning');
        return;
    }
    if (!confirm(`Bắt đầu cập nhật OTA từ: ${url}?`)) return;
    try {
        await api.startOTACamera(CAMERA_ID, url);
        window.ui?.toast('Đã gửi lệnh OTA. Vui lòng theo dõi trạng thái thiết bị.', 'success');
    } catch (error) {
        window.ui?.toast(`Lỗi OTA: ${error.message}`, 'error');
    }
}

function startOverlayClock() {
    setInterval(() => {
        const element = document.getElementById('overlayClock');
        if (element) element.textContent = new Date().toLocaleTimeString('vi-VN');
    }, 1000);
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value ?? '--';
}
