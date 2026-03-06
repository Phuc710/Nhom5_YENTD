/**
 * camera.js — Trang camera detail: stream + zone editor + edit config
 */

let zoneEditor = null;
let currentCamera = null;
const CAMERA_ID = window.APP_CONFIG?.CAMERA_ID;

document.addEventListener('DOMContentLoaded', async () => {
    await loadCamera();
    await loadCameraViolations();
    initZoneEditor();
    await loadZones();
});

// ---- Load camera data -----------------------------------
async function loadCamera() {
    try {
        currentCamera = await api.getCamera(CAMERA_ID);
        renderCameraInfo(currentCamera);
    } catch (e) {
        console.error('Load camera:', e);
    }
}

function renderCameraInfo(c) {
    document.title = `${c.camera_name} — ${window.APP_CONFIG?.APP_NAME || 'YTD'}`;
    setText('camTitle', c.camera_name);
    setText('camLocation', c.location);
    setText('infoId', c.camera_id);
    setText('infoName', c.camera_name);
    setText('infoLoc', c.location);
    setText('infoIp', c.ip_address || '—');
    setText('infoMac', c.mac_address || '—');
    setText('infoFw', c.fw_version || '—');
    setText('infoSeen', c.last_seen_at ? formatDateVN(c.last_seen_at) : '—');
    setText('infoStream', c.stream_url || '—');

    const dot = document.getElementById('onlineDot');
    dot.className = `status-dot status-dot--${c.online ? 'online' : 'offline'}`;

    if (c.latitude && c.longitude) {
        const mapEl = document.getElementById('infoMap');
        mapEl.href = `https://www.google.com/maps?q=${c.latitude},${c.longitude}`;
    }

    // Set stream image
    if (c.stream_url) {
        const img = document.getElementById('streamImg');
        img.src = c.stream_url;
        img.style.display = 'block';
        document.getElementById('noStream').style.display = 'none';
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val ?? '—';
}

// ---- Zone editor ----------------------------------------
function initZoneEditor() {
    const wrap = document.getElementById('streamWrap');
    const imgEl = document.getElementById('streamImg');
    if (!wrap || !imgEl) return;

    zoneEditor = new ZoneEditor(wrap, imgEl);

    zoneEditor.on('change', zones => {
        document.getElementById('zoneJsonPreview').textContent = JSON.stringify(zones, null, 2);
    });

    zoneEditor.on('select', zone => {
        const zi = document.getElementById('zoneInfo');
        if (!zone) { zi.style.display = 'none'; return; }
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
        const zones = await api.getZones(CAMERA_ID);
        zoneEditor.loadZones(zones);
        document.getElementById('zoneJsonPreview').textContent =
            JSON.stringify(zoneEditor.getZones(), null, 2);
    } catch (e) { console.error('Load zones:', e); }
}

async function saveZones() {
    if (!zoneEditor) return;
    const btn = document.getElementById('btnSaveZones');
    btn.disabled = true;
    btn.textContent = 'Đang lưu...';
    try {
        await api.saveZones(CAMERA_ID, zoneEditor.getZones());
        btn.textContent = '✅ Đã lưu!';
        setTimeout(() => { btn.disabled = false; btn.innerHTML = `<svg viewBox="0 0 20 20" fill="currentColor"><path d="M7.707 10.293a1 1 0 10-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L11 11.586V6h5a2 2 0 012 2v7a2 2 0 01-2 2H4a2 2 0 01-2-2V8a2 2 0 012-2h5v5.586l-1.293-1.293z"/></svg> Lưu Zones`; }, 2000);
    } catch (e) {
        alert('Lỗi lưu zones: ' + e.message);
        btn.disabled = false;
        btn.textContent = 'Lưu Zones';
    }
}

function setZoneType(type) { if (zoneEditor) zoneEditor.setZoneType(type); }
function clearZones() { if (zoneEditor) zoneEditor.clearAll(); }

// ---- Edit config modal ----------------------------------
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
    document.getElementById('editModal').classList.remove('hidden');
}

function closeEditModal() { document.getElementById('editModal').classList.add('hidden'); }

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
        currentCamera = await api.updateCamera(CAMERA_ID, payload);
        renderCameraInfo(currentCamera);
        closeEditModal();
    } catch (e) {
        alertEl.innerHTML = `<div class="alert alert--error">${e.message}</div>`;
    }
}

// ---- Camera violations ----------------------------------
async function loadCameraViolations() {
    const tbody = document.getElementById('camViolations');
    try {
        const viols = await api.getViolations({ camera_id: CAMERA_ID, limit: 8 });
        if (!viols.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px;color:#9CA3AF">Chưa có vi phạm</td></tr>';
            return;
        }
        tbody.innerHTML = viols.map(v => `
    <tr>
      <td>${v.full_image_url ? `<img class="thumb" src="${v.full_image_url}" alt="">` : '—'}</td>
      <td>${plateBadge(v.license_plate)}</td>
      <td style="font-size:12px">${formatDateVN(v.timestamp)}</td>
      <td><a href="/violation-detail.php?id=${v.id}" class="btn btn--outline btn--sm">Chi tiết</a></td>
    </tr>`).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" class="alert alert--error">Lỗi: ${e.message}</td></tr>`;
    }
}
