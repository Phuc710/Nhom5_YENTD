let zoneEditor = null;
let currentCamera = null;
const CAMERA_ID = window.APP_CONFIG?.CAMERA_ID;

document.addEventListener('DOMContentLoaded', async () => {
    initZoneEditor();
    await loadZones();

    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: `camera-detail-${CAMERA_ID}`,
            resources: ['cameras', 'summary'],
            intervalVisible: 12_000,
            intervalHidden: 90_000,
            run: () => api.getCamera(CAMERA_ID, { requestKey: `camera-detail-${CAMERA_ID}` }),
            onData: (camera) => {
                currentCamera = camera;
                renderCameraInfo(camera);
            },
        });

        window.liveDataHub.register({
            id: `camera-violations-${CAMERA_ID}`,
            resources: ['violations', 'summary'],
            intervalVisible: 10_000,
            intervalHidden: 90_000,
            run: () => api.getViolations({ camera_id: CAMERA_ID, limit: 8 }, { requestKey: `camera-violations-${CAMERA_ID}` }),
            onData: renderCameraViolations,
            onError: renderCameraViolationError,
        });

        window.liveDataHub.register({
            id: `camera-zones-${CAMERA_ID}`,
            resources: ['zones'],
            intervalVisible: 45_000,
            intervalHidden: 120_000,
            run: () => api.getZones(CAMERA_ID, { requestKey: `camera-zones-${CAMERA_ID}` }),
            onData: renderZones,
        });
        return;
    }

    await loadCameraFallback();
    await loadCameraViolationsFallback();
});

async function loadCameraFallback() {
    try {
        currentCamera = await api.getCamera(CAMERA_ID);
        renderCameraInfo(currentCamera);
    } catch (error) {
        console.error('Load camera:', error);
    }
}

function renderCameraInfo(camera) {
    document.title = `${camera.camera_name} - ${window.APP_CONFIG?.APP_NAME || 'YTD'}`;
    setText('camTitle', camera.camera_name);
    setText('camLocation', camera.location || 'Chua co vi tri');
    setText('infoId', camera.camera_id);
    setText('infoName', camera.camera_name);
    setText('infoLoc', camera.location || 'Chua co vi tri');
    setText('infoIp', camera.ip_address || '--');
    setText('infoMac', camera.mac_address || '--');
    setText('infoFw', camera.fw_version || '--');
    setText('infoSeen', camera.last_seen_at ? formatDateVN(camera.last_seen_at) : '--');
    setText('infoStream', camera.stream_url || '--');

    const dot = document.getElementById('onlineDot');
    dot.className = `status-dot status-dot--${camera.online ? 'online' : 'offline'}`;

    const mapEl = document.getElementById('infoMap');
    if (camera.latitude && camera.longitude) {
        mapEl.href = `https://www.google.com/maps?q=${camera.latitude},${camera.longitude}`;
        mapEl.removeAttribute('aria-disabled');
    } else {
        mapEl.href = '#';
        mapEl.setAttribute('aria-disabled', 'true');
    }

    const img = document.getElementById('streamImg');
    const noStream = document.getElementById('noStream');
    const statusEl = document.getElementById('streamStatus');
    if (camera.stream_url) {
        img.src = camera.stream_url;
        img.style.display = 'block';
        noStream.style.display = 'none';
        statusEl.textContent = camera.online ? 'Live' : 'Co stream URL';
        statusEl.className = `badge ${camera.online ? 'badge--green' : 'badge--gray'}`;
    } else {
        img.removeAttribute('src');
        img.style.display = 'none';
        noStream.style.display = 'flex';
        noStream.textContent = 'Chua cau hinh stream URL';
        statusEl.textContent = 'Chua co stream';
        statusEl.className = 'badge badge--gray';
    }
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? '--';
}

function initZoneEditor() {
    const wrap = document.getElementById('streamWrap');
    const imgEl = document.getElementById('streamImg');
    if (!wrap || !imgEl) return;

    zoneEditor = new ZoneEditor(wrap, imgEl);

    zoneEditor.on('change', (zones) => {
        document.getElementById('zoneJsonPreview').textContent = JSON.stringify(zones, null, 2);
    });

    zoneEditor.on('select', (zone) => {
        const zi = document.getElementById('zoneInfo');
        if (!zone) {
            zi.style.display = 'none';
            return;
        }
        zi.style.display = 'grid';
        document.getElementById('ziX').value = zone.x;
        document.getElementById('ziY').value = zone.y;
        document.getElementById('ziW').value = zone.width;
        document.getElementById('ziH').value = zone.height;
    });
}

async function loadZones() {
    if (!zoneEditor) return;
    try {
        renderZones(await api.getZones(CAMERA_ID));
    } catch (error) {
        console.error('Load zones:', error);
    }
}

function renderZones(zones) {
    if (!zoneEditor || !Array.isArray(zones)) return;
    zoneEditor.loadZones(zones);
    document.getElementById('zoneJsonPreview').textContent = JSON.stringify(zoneEditor.getZones(), null, 2);
}

async function saveZones() {
    if (!zoneEditor) return;
    const btn = document.getElementById('btnSaveZones');
    btn.disabled = true;
    btn.textContent = 'Dang luu...';
    try {
        const zones = await api.saveZones(CAMERA_ID, zoneEditor.getZones(), { requestKey: `save-zones-${CAMERA_ID}` });
        renderZones(zones);
        btn.textContent = 'Da luu';
        if (window.liveDataHub) {
            window.liveDataHub.requestSync({ resources: ['zones'], reason: 'save-zones' });
        }
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = 'Luu zone';
        }, 1500);
    } catch (error) {
        alert(`Loi luu zone: ${error.message}`);
        btn.disabled = false;
        btn.textContent = 'Luu zone';
    }
}

function setZoneType(type) {
    if (zoneEditor) zoneEditor.setZoneType(type);
}

function clearZones() {
    if (zoneEditor) zoneEditor.clearAll();
}

function openEditModal() {
    if (!currentCamera) return;
    document.getElementById('editName').value = currentCamera.camera_name || '';
    document.getElementById('editLoc').value = currentCamera.location || '';
    document.getElementById('editLat').value = currentCamera.latitude || '';
    document.getElementById('editLng').value = currentCamera.longitude || '';
    document.getElementById('editStream').value = currentCamera.stream_url || '';
    document.getElementById('editTbName').value = currentCamera.tb_device_name || '';
    document.getElementById('editDesc').value = currentCamera.description || '';
    document.getElementById('editAlert').innerHTML = '';
    document.getElementById('factoryResetAlert').innerHTML = '';
    document.getElementById('btnFactoryReset').disabled = false;
    document.getElementById('btnFactoryReset').textContent = 'Factory reset thiet bi';
    document.getElementById('editModal').classList.remove('hidden');
}

function closeEditModal() {
    document.getElementById('editModal').classList.add('hidden');
}

async function saveConfig() {
    const alertEl = document.getElementById('editAlert');
    alertEl.innerHTML = '';
    const payload = {
        camera_name: document.getElementById('editName').value.trim(),
        location: document.getElementById('editLoc').value.trim(),
        latitude: parseFloat(document.getElementById('editLat').value) || null,
        longitude: parseFloat(document.getElementById('editLng').value) || null,
        stream_url: document.getElementById('editStream').value.trim() || null,
        tb_device_name: document.getElementById('editTbName').value.trim() || null,
        description: document.getElementById('editDesc').value.trim() || null,
    };

    try {
        currentCamera = await api.updateCamera(CAMERA_ID, payload, { requestKey: `save-camera-${CAMERA_ID}` });
        renderCameraInfo(currentCamera);
        closeEditModal();
        if (window.liveDataHub) {
            window.liveDataHub.requestSync({ resources: ['cameras', 'summary'], reason: 'save-camera' });
        }
    } catch (error) {
        alertEl.innerHTML = `<div class="alert alert--error">${error.message}</div>`;
    }
}

async function factoryResetCamera() {
    const alertEl = document.getElementById('factoryResetAlert');
    const btn = document.getElementById('btnFactoryReset');
    alertEl.innerHTML = '';

    if (!currentCamera) return;

    const confirmed = window.confirm(
        `Xoa toan bo NVS cua camera ${currentCamera.camera_name || `#${CAMERA_ID}`}?\n\nThiet bi se mat toan bo cau hinh da luu va khoi dong lai.`
    );
    if (!confirmed) return;

    btn.disabled = true;
    btn.textContent = 'Dang gui lenh reset...';

    try {
        const result = await api.factoryResetCamera(CAMERA_ID, { requestKey: `factory-reset-${CAMERA_ID}` });
        alertEl.innerHTML = `<div class="alert alert--success">${result?.message || 'Da gui lenh factory reset toi thiet bi.'}</div>`;
        btn.textContent = 'Da gui lenh factory reset';
    } catch (error) {
        alertEl.innerHTML = `<div class="alert alert--error">${error.message}</div>`;
        btn.disabled = false;
        btn.textContent = 'Factory reset thiet bi';
    }
}

async function loadCameraViolationsFallback() {
    try {
        renderCameraViolations(await api.getViolations({ camera_id: CAMERA_ID, limit: 8 }));
    } catch (error) {
        renderCameraViolationError(error);
    }
}

function renderCameraViolations(violations) {
    const tbody = document.getElementById('camViolations');
    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:#9CA3AF">Chua co vi pham</td></tr>';
        return;
    }
    tbody.innerHTML = violations.map((violation) => `
        <tr>
            <td>${violation.full_image_url ? `<img class="thumb" src="${violation.full_image_url}" alt="">` : '--'}</td>
            <td>${plateBadge(violation.license_plate)}</td>
            <td style="font-size:12px">${formatDateVN(violation.timestamp)}</td>
            <td><a href="/violation-detail.php?id=${violation.id}" class="btn btn--outline btn--sm">Chi tiet</a></td>
        </tr>
    `).join('');
}

function renderCameraViolationError(error) {
    const tbody = document.getElementById('camViolations');
    tbody.innerHTML = `<tr><td colspan="4" class="alert alert--error">Loi tai vi pham: ${error.message}</td></tr>`;
}
