/**
 * violations.js — list, filter, pagination
 */
let currentPage = 1;
const LIMIT = 20;
let currentFilters = {};

document.addEventListener('DOMContentLoaded', async () => {
    await loadCameraOptions();
    // Pre-fill camera_id from URL
    const urlParams = new URLSearchParams(location.search);
    if (urlParams.get('camera_id')) {
        document.getElementById('fCamera').value = urlParams.get('camera_id');
        currentFilters.camera_id = parseInt(urlParams.get('camera_id'));
    }
    await loadViolations();
});

async function loadCameraOptions() {
    try {
        const cameras = await api.getCameras();
        const sel = document.getElementById('fCamera');
        cameras.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.camera_id;
            opt.textContent = c.camera_name;
            sel.appendChild(opt);
        });
    } catch (e) { console.error('cams:', e); }
}

function applyFilter() {
    currentPage = 1;
    currentFilters = {
        camera_id: document.getElementById('fCamera').value || null,
        license_plate: document.getElementById('fPlate').value.trim() || null,
        date_from: document.getElementById('fFrom').value || null,
        date_to: document.getElementById('fTo').value || null,
    };
    loadViolations();
}

function resetFilter() {
    document.getElementById('fCamera').value = '';
    document.getElementById('fPlate').value = '';
    document.getElementById('fFrom').value = '';
    document.getElementById('fTo').value = '';
    currentFilters = {};
    currentPage = 1;
    loadViolations();
}

async function loadViolations() {
    const tbody = document.getElementById('violTableBody');
    tbody.innerHTML = '<tr><td colspan="8" class="loading">Đang tải...</td></tr>';
    try {
        const data = await api.getViolations({ ...currentFilters, page: currentPage, limit: LIMIT });
        document.getElementById('totalBadge').textContent = `${data.length} kết quả`;

        if (!data.length) {
            tbody.innerHTML = '<tr><td colspan="8"><div class="empty-state" style="padding:40px">Không có vi phạm nào</div></td></tr>';
            renderPagination(0);
            return;
        }

        tbody.innerHTML = data.map(v => `
    <tr>
      <td>${v.full_image_url ? `<img class="thumb" src="${v.full_image_url}" alt="">` : '—'}</td>
      <td>${plateBadge(v.license_plate)}</td>
      <td>
        <a href="/camera.php?id=${v.camera_id}" style="font-weight:600;font-size:13px;">${v.camera_name || v.camera_id}</a>
        <div style="font-size:11px;color:#9CA3AF;margin-top:2px">${v.location || ''}</div>
      </td>
      <td style="font-size:12px;white-space:nowrap">${formatDateVN(v.timestamp)}</td>
      <td>${lightBadge(v.traffic_light_state)}</td>
      <td style="font-size:12px">${v.confidence ? (v.confidence * 100).toFixed(1) + '%' : '—'}</td>
      <td><span class="badge badge--gray" style="font-size:11px">${v.violation_type || 'red_light'}</span></td>
      <td><a href="/violation-detail.php?id=${v.id}" class="btn btn--outline btn--sm">Chi tiết</a></td>
    </tr>`).join('');

        renderPagination(data.length);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8"><div class="alert alert--error">Lỗi: ${e.message}</div></td></tr>`;
    }
}

function renderPagination(count) {
    const bar = document.getElementById('paginationBar');
    const hasPrev = currentPage > 1;
    const hasNext = count === LIMIT;
    bar.innerHTML = `
    <button class="page-btn" ${!hasPrev ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">← Trước</button>
    <span class="page-btn page-btn--active">Trang ${currentPage}</span>
    <button class="page-btn" ${!hasNext ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">Sau →</button>`;
}

function changePage(p) {
    currentPage = p;
    loadViolations();
    window.scrollTo(0, 0);
}
