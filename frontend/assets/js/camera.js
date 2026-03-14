let currentCamera = null;
let streamConnected = false;
let zoneEditor = null;
const CAMERA_ID = window.APP_CONFIG?.CAMERA_ID;

document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    startOverlayClock();
    bindUploadUI();
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

function bindUploadUI() {
    const button = document.getElementById('btnDetectUpload');
    if (!button) return;
    button.addEventListener('click', detectUploadImage);
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
        setText('zoneStatus', `${zones.length} zone chua luu`);
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
        setText('zoneStatus', 'Da xoa zone tam, chua luu');
    });
    saveBtn?.addEventListener('click', saveZones);
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
    setText('streamInfo', 'MJPEG via backend proxy + detect preview 2s/lan');
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
    setText('streamInfo', `Loi detect preview: ${error.message}`);
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
        const stopText = item.matched_stop_lines?.length ? ` | stop:${item.matched_stop_lines.join(', ')}` : '';
        const vioText = item.is_violation ? ' | VI PHAM' : item.crossed_stop_line ? ' | cham vach' : '';
        label.textContent = `${item.plate_text || 'Khong ro'} | ${((item.confidence || 0) * 100).toFixed(1)}%${zoneText}${stopText}${vioText}`;
        box.appendChild(label);
        layer.appendChild(box);
    });
}

function renderZones(zones) {
    if (!zoneEditor) return;
    zoneEditor.loadZones(zones || []);
    setText('zoneStatus', `${(zones || []).length} zone dang hoat dong`);
}

function renderZoneError(error) {
    setText('zoneStatus', `Loi zone: ${error.message}`);
}

function renderCameraViolations(violations) {
    const tbody = document.getElementById('recentList');
    if (!tbody) return;
    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px;" class="text-muted">Chua co vi pham nao.</td></tr>';
        return;
    }

    tbody.innerHTML = violations.map((item) => `
        <tr>
            <td><img src="${item.cropped_plate_url || item.full_image_url}" style="width:60px; height:36px; border-radius:2px; object-fit:cover;"></td>
            <td><span class="badge" style="background:#222; border:1px solid #333; color:#fff; font-family:monospace; font-size:1rem;">${item.license_plate || '---'}</span></td>
            <td style="font-size:0.8rem; color:var(--color-text-dim)">${formatDateVN(item.timestamp)}</td>
            <td style="font-weight:700; color:var(--color-primary)">${item.confidence ? `${(item.confidence * 100).toFixed(1)}%` : '--'}</td>
            <td><a href="/violation-detail?id=${item.id}" class="btn btn--outline" style="padding:4px 8px; font-size:0.75rem;">Chi tiet</a></td>
        </tr>
    `).join('');
}

function renderCameraViolationError(error) {
    const tbody = document.getElementById('recentList');
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="color:var(--color-error); text-align:center;">Loi: ${error.message}</td></tr>`;
}

async function detectUploadImage() {
    const input = document.getElementById('detectUploadInput');
    const status = document.getElementById('detectUploadStatus');
    const summary = document.getElementById('detectUploadSummary');
    const results = document.getElementById('detectUploadResults');
    const file = input?.files?.[0];

    if (!file) {
        if (status) status.textContent = 'Hay chon anh truoc';
        return;
    }

    const formData = new FormData();
    formData.append('image', file);
    formData.append('traffic_light_state', String(currentCamera?.light_mode || 'green').toLowerCase());
    if (currentCamera?.location) {
        formData.append('location', currentCamera.location);
    }

    if (status) status.textContent = 'Dang detect...';
    if (summary) summary.textContent = '';
    if (results) results.innerHTML = '';

    try {
        const payload = await api.detectUploadCamera(CAMERA_ID, formData, { requestKey: `detect-upload-${CAMERA_ID}` });
        if (status) status.textContent = 'Detect xong';
        if (summary) {
            summary.textContent = `Tim thay ${payload.detected_count || 0} BSX, luu ${payload.saved_count || 0} vi pham.`;
        }
        if (results) {
            const items = payload.items || [];
            results.innerHTML = items.length
                ? items.map(renderDetectResultCard).join('')
                : '<div class="text-dim">Khong thay BSX nao trong anh.</div>';
        }
        if (window.liveDataHub) {
            window.liveDataHub.trigger?.(['violations', 'stream']);
        }
    } catch (error) {
        if (status) status.textContent = 'Detect loi';
        if (summary) summary.textContent = error.message;
        if (results) results.innerHTML = '';
    }
}

function renderDetectResultCard(item) {
    const savedBadge = item.violation_saved
        ? '<span class="badge badge--green">Da luu</span>'
        : item.duplicate
            ? '<span class="badge badge--yellow">Trung</span>'
            : item.is_violation
                ? '<span class="badge badge--gray">Chua luu</span>'
                : '<span class="badge badge--gray">Khong vi pham</span>';

    return `
        <article class="detect-card">
            <div class="detect-card__images">
                <img src="${item.vehicle_image_url || ''}" alt="Vehicle evidence">
                <img src="${item.plate_image_url || ''}" alt="Plate crop">
            </div>
            <div class="detect-card__body">
                <div class="detect-card__plate">${item.license_plate || 'KHONG RO'}</div>
                <div class="text-dim">Tin cay: ${item.confidence ? `${(item.confidence * 100).toFixed(1)}%` : '--'}</div>
                <div>${savedBadge}</div>
                <div class="text-dim">${item.violation?.id ? `Violation #${item.violation.id}` : 'Chua tao ID'}</div>
                <div class="text-dim">Zone: ${item.matched_zones?.join(', ') || '--'}</div>
                <div class="text-dim">Stop line: ${item.matched_stop_lines?.join(', ') || '--'}</div>
                <div class="text-dim">BBox: ${formatBbox(item.bbox)}</div>
            </div>
        </article>
    `;
}

function formatBbox(bbox) {
    if (!bbox) return '--';
    return `${bbox.x1},${bbox.y1},${bbox.x2},${bbox.y2}`;
}

async function setLight(state) {
    try {
        await api.setTrafficLightState?.(CAMERA_ID, state);
        window.ui?.toast(`Da doi sang: ${state.toUpperCase()}`, 'success');
    } catch (error) {
        window.ui?.toast(`Loi dieu khien: ${error.message}`, 'error');
    }
}

async function saveSettings() {
    const payload = {
        camera_name: document.getElementById('cfgName').value.trim(),
        location: document.getElementById('cfgLocation').value.trim(),
    };
    try {
        await api.updateCamera(CAMERA_ID, payload);
        window.ui?.toast('Da luu cau hinh', 'success');
    } catch (error) {
        window.ui?.toast(`Loi luu: ${error.message}`, 'error');
    }
}

async function saveZones() {
    if (!zoneEditor) return;
    const zones = zoneEditor.getZones();
    setText('zoneStatus', 'Dang luu zones...');
    try {
        const saved = await api.saveZones(CAMERA_ID, zones, { requestKey: `save-zones-${CAMERA_ID}` });
        renderZones(saved);
        window.ui?.toast('Da luu zones', 'success');
    } catch (error) {
        setText('zoneStatus', `Loi luu zone: ${error.message}`);
        window.ui?.toast(`Loi zone: ${error.message}`, 'error');
    }
}

async function factoryReset() {
    if (!confirm('Xac nhan factory reset camera nay?')) return;
    try {
        await api.factoryResetCamera(CAMERA_ID);
        window.ui?.toast('Da gui lenh reset', 'success');
    } catch (error) {
        window.ui?.toast(`Loi: ${error.message}`, 'error');
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
