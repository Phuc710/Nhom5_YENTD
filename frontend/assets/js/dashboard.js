/**
 * dashboard.js — Tải dữ liệu cho Dashboard
 */
document.addEventListener('DOMContentLoaded', async () => {
    await Promise.all([loadSummary(), loadCameras(), loadRecent()]);
    // Auto-refresh mỗi 30s
    setInterval(() => Promise.all([loadSummary(), loadRecent()]), 30_000);
});

async function loadSummary() {
    try {
        const s = await api.getSummary();
        document.getElementById('statToday').textContent = s.violations_today ?? 0;
        document.getElementById('statOnline').textContent = s.online_cameras ?? 0;
        document.getElementById('statTotal').textContent = `/ ${s.total_cameras ?? 0} cameras`;
        document.getElementById('statAll').textContent = s.violations_total ?? 0;
    } catch (e) { console.error('Summary:', e); }
}

async function loadCameras() {
    const grid = document.getElementById('cameraGrid');
    try {
        const cameras = await api.getCameras();
        document.getElementById('cameraCountBadge').textContent = `${cameras.length} cameras`;
        if (!cameras.length) {
            grid.innerHTML = '<p class="empty-state">Chưa có camera nào.</p>';
            return;
        }
        grid.innerHTML = cameras.map(c => renderCameraCard(c)).join('');
    } catch (e) {
        grid.innerHTML = `<div class="alert alert--error">Lỗi tải cameras: ${e.message}</div>`;
    }
}

function renderCameraCard(c) {
    const online = c.online;
    const lastSeen = c.last_seen_at ? formatDateVN(c.last_seen_at) : '—';
    const streamPreview = c.stream_url
        ? `<img class="cam-card__thumb" src="${c.stream_url}" alt="Stream" loading="lazy" onerror="this.style.display='none'">`
        : `<div class="cam-card__no-stream">Chưa có stream</div>`;

    return `
  <a href="/camera.php?id=${c.camera_id}" class="cam-card">
    <div class="cam-card__preview">
      ${streamPreview}
      <span class="cam-card__status">
        <span class="status-dot status-dot--${online ? 'online' : 'offline'}"></span>
        ${online ? 'Online' : 'Offline'}
      </span>
    </div>
    <div class="cam-card__body">
      <div class="cam-card__name">${c.camera_name}</div>
      <div class="cam-card__loc">
        <svg viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"/></svg>
        ${c.location}
      </div>
      <div class="cam-card__stats">
        <span class="cam-card__stat"><strong>${c.violations_today ?? 0}</strong> hôm nay</span>
        <span class="cam-card__stat">${c.fw_version ? 'fw: ' + c.fw_version : 'Chưa kết nối'}</span>
      </div>
      <div class="cam-card__lastseen">Lần cuối: ${lastSeen}</div>
    </div>
  </a>`;
}

async function loadRecent() {
    const tbody = document.getElementById('recentTableBody');
    try {
        const viols = await api.getRecentViolations(10);
        if (!viols.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-state" style="padding:32px;text-align:center">Chưa có vi phạm</td></tr>';
            return;
        }
        tbody.innerHTML = viols.map(v => `
    <tr>
      <td>${v.full_image_url ? `<img class="thumb" src="${v.full_image_url}" alt="">` : '—'}</td>
      <td>${plateBadge(v.license_plate)}</td>
      <td>${v.camera_name || v.camera_id}</td>
      <td>${formatDateVN(v.timestamp)}</td>
      <td>${lightBadge(v.traffic_light_state)}</td>
      <td>${v.confidence ? (v.confidence * 100).toFixed(1) + '%' : '—'}</td>
      <td><a href="/violation-detail.php?id=${v.id}" class="btn btn--outline btn--sm">Chi tiết</a></td>
    </tr>`).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="7" class="alert alert--error">Lỗi: ${e.message}</td></tr>`;
    }
}
