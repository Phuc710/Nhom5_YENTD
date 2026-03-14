let currentCamera = null;
let currentLiveView = null;
let clockTimer = null;
let streamConnected = false;
let streamAttempt = 0;
const CAMERA_ID = window.APP_CONFIG?.CAMERA_ID;

document.addEventListener('DOMContentLoaded', async () => {
    initTabs();
    startOverlayClock();

    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: `camera-detail-${CAMERA_ID}`,
            resources: ['cameras'],
            intervalVisible: 12_000,
            intervalHidden: 90_000,
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
            intervalHidden: 12_000,
            run: () => api.getCameraLiveView(CAMERA_ID, { requestKey: `camera-live-${CAMERA_ID}` }),
            onData: renderLiveView,
            onError: renderLiveViewError,
        });

        window.liveDataHub.register({
            id: `camera-violations-${CAMERA_ID}`,
            resources: ['violations'],
            intervalVisible: 10_000,
            intervalHidden: 90_000,
            run: () => api.getViolations({ camera_id: CAMERA_ID, limit: 10 }, { requestKey: `camera-violations-${CAMERA_ID}` }),
            onData: renderCameraViolations,
            onError: renderCameraViolationError,
        });
        return;
    }

    // Fallback logic
    refreshFallback();
    setInterval(refreshFallback, 5000);
});

async function refreshFallback() {
    try {
        const [camera, live, violations] = await Promise.all([
            api.getCamera(CAMERA_ID),
            api.getCameraLiveView(CAMERA_ID),
            api.getViolations({ camera_id: CAMERA_ID, limit: 10 })
        ]);
        currentCamera = camera;
        renderCameraInfo(camera);
        syncSettingsForm(camera);
        renderLiveView(live);
        renderCameraViolations(violations);
    } catch (e) {
        console.error('Fallback refresh failed', e);
    }
}

function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.add('hidden'));
            btn.classList.add('active');

            // Map tab-tabId to ID
            const targetId = 'tab' + tabId.charAt(0).toUpperCase() + tabId.slice(1);
            const target = document.getElementById(targetId);
            if (target) target.classList.remove('hidden');
        });
    });
}

function renderCameraInfo(camera) {
    setText('camStatus', camera.online ? 'Online' : 'Offline');
    setText('camIp', camera.ip_address || '--');
    setText('camMac', camera.mac_address || '--');
    setText('camFw', camera.fw_version || '--');

    // Auto-connect stream if available
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
    setText('streamInfo', 'Đang truyền trực tiếp (via Backend Proxy)');
}

function renderLiveView(payload) {
    if (!payload) return;
    const overlay = payload.overlay || {};

    // Update lights
    const state = (overlay.traffic_light_state || 'none').toLowerCase();
    document.getElementById('dotRed').classList.toggle('active', state === 'red');
    document.getElementById('dotYellow').classList.toggle('active', state === 'yellow');
    document.getElementById('dotGreen').classList.toggle('active', state === 'green');

    setText('overlayFps', (overlay.fps || '--') + ' FPS');
}

function renderLiveViewError(err) {
    setText('streamInfo', 'Lỗi: ' + err.message);
}

function renderCameraViolations(violations) {
    const tbody = document.getElementById('recentList');
    if (!tbody) return;
    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding:40px;" class="text-muted">Chưa có vi phạm nào.</td></tr>';
        return;
    }

    tbody.innerHTML = violations.map(v => `
        <tr>
            <td><img src="${v.cropped_plate_url || v.full_image_url}" style="width:60px; height:36px; border-radius:2px; object-fit:cover;"></td>
            <td><span class="badge" style="background:#222; border:1px solid #333; color:#fff; font-family:monospace; font-size:1rem;">${v.license_plate || '---'}</span></td>
            <td style="font-size:0.8rem; color:var(--color-text-dim)">${formatDateVN(v.timestamp)}</td>
            <td style="font-weight:700; color:var(--color-primary)">${v.confidence ? (v.confidence * 100).toFixed(1) + '%' : '--'}</td>
            <td><a href="/violation-detail?id=${v.id}" class="btn btn--outline" style="padding:4px 8px; font-size:0.75rem;">Chi tiết</a></td>
        </tr>
    `).join('');
}

function renderCameraViolationError(err) {
    const tbody = document.getElementById('recentList');
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="color:var(--color-error); text-align:center;">Lỗi: ${err.message}</td></tr>`;
}

async function setLight(state) {
    try {
        await api.setTrafficLightState(CAMERA_ID, state);
    } catch (e) {
        alert('Lỗi điều khiển: ' + e.message);
    }
}

async function saveSettings() {
    const payload = {
        camera_name: document.getElementById('cfgName').value.trim(),
        location: document.getElementById('cfgLocation').value.trim()
    };
    try {
        await api.updateCamera(CAMERA_ID, payload);
        alert('Đã lưu cấu hình!');
    } catch (e) {
        alert('Lỗi lưu: ' + e.message);
    }
}

async function factoryReset() {
    if (!confirm('XÁC NHẬN: Bạn muốn khôi phục cài đặt gốc? Toàn bộ cấu hình sẽ mất.')) return;
    try {
        await api.factoryResetCamera(CAMERA_ID);
        alert('Đã gửi lệnh Reset!');
    } catch (e) {
        alert('Lỗi: ' + e.message);
    }
}

function startOverlayClock() {
    setInterval(() => {
        const el = document.getElementById('overlayClock');
        if (el) el.textContent = new Date().toLocaleTimeString('vi-VN');
    }, 1000);
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val ?? '--';
}
