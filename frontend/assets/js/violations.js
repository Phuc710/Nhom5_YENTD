let currentPage = 1;
const LIMIT = 20;
let currentFilters = {
    date_from: null,
    date_to: null,
    camera_id: null,
    license_plate: null
};
let searchTimeout = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadCameraOptions();

    const urlParams = new URLSearchParams(location.search);
    if (urlParams.get('camera_id')) {
        document.getElementById('fCamera').value = urlParams.get('camera_id');
        currentFilters.camera_id = parseInt(urlParams.get('camera_id'), 10);
    }

    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: 'violations-list',
            resources: ['violations', 'summary', 'cameras'],
            intervalVisible: 15_000,
            intervalHidden: 90_000,
            run: () => api.getViolations({ ...currentFilters, page: currentPage, limit: LIMIT }, { requestKey: 'violations-list' }),
            onData: renderViolations,
            onError: renderViolationsError,
        });
        return;
    }

    await loadViolationsFallback();
});

async function loadCameraOptions() {
    try {
        const cameras = await api.getCameras({ requestKey: 'violations-camera-options' });
        const sel = document.getElementById('fCamera');
        cameras.forEach((camera) => {
            const opt = document.createElement('option');
            opt.value = camera.camera_id;
            opt.textContent = camera.camera_name;
            sel.appendChild(opt);
        });
    } catch (error) {
        console.error('Load camera options:', error);
    }
}

function setDateRange(range, btn) {
    // UI toggle
    document.querySelectorAll('.btn--outline').forEach(b => b.classList.remove('active-preset'));
    if (btn) btn.classList.add('active-preset');

    const now = new Date();
    const today = now.toISOString().split('T')[0];

    currentFilters.date_to = today;

    if (range === 'today') {
        currentFilters.date_from = today;
    } else if (range === '7d') {
        const d = new Date();
        d.setDate(d.getDate() - 7);
        currentFilters.date_from = d.toISOString().split('T')[0];
    } else if (range === '1m') {
        const d = new Date();
        d.setMonth(d.getMonth() - 1);
        currentFilters.date_from = d.toISOString().split('T')[0];
    } else {
        currentFilters.date_from = null;
        currentFilters.date_to = null;
    }

    applyFilter();
}

function onSearchInput() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentFilters.license_plate = document.getElementById('fPlate').value.trim() || null;
        applyFilter();
    }, 500); // Debounce 500ms
}

function applyFilter() {
    currentPage = 1;
    // Camera filter
    currentFilters.camera_id = document.getElementById('fCamera').value || null;

    if (window.liveDataHub) {
        window.liveDataHub.requestSync({ resources: ['violations'], reason: 'filter-change' });
        return;
    }

    loadViolationsFallback();
}

function resetFilter() {
    document.getElementById('fPlate').value = '';
    document.getElementById('fCamera').value = '';
    setDateRange('all', document.querySelector('[data-range="all"]'));
}

async function loadViolationsFallback() {
    try {
        renderViolations(await api.getViolations({ ...currentFilters, page: currentPage, limit: LIMIT }));
    } catch (error) {
        renderViolationsError(error);
    }
}

function renderViolations(data) {
    const tbody = document.getElementById('violTableBody');
    document.getElementById('totalBadge').textContent = `${data.length} kết quả`;

    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="8"><div class="empty-state" style="padding:40px">Không có vi phạm nào</div></td></tr>';
        renderPagination(0);
        return;
    }

    tbody.innerHTML = data.map((violation) => `
        <tr>
            <td>
                ${violation.cropped_vehicle_url || violation.stop_line_snapshot_url || violation.full_image_url
            ? `<img class="thumb" src="${violation.cropped_vehicle_url || violation.stop_line_snapshot_url || violation.full_image_url}" alt="">`
            : '--'}
            </td>
            <td>${plateBadge(violation.license_plate)}</td>
            <td>
                <a href="/camera/${violation.camera_id}" style="font-weight:600;font-size:13px;">${violation.camera_name || violation.camera_id}</a>
                <div style="font-size:11px;color:#9CA3AF;margin-top:2px">${violation.location || ''}</div>
            </td>
            <td style="font-size:12px;white-space:nowrap">${formatDateVN(violation.timestamp)}</td>
            <td>${lightBadge(violation.traffic_light_state)}</td>
            <td style="font-size:12px">${violation.confidence ? `${(violation.confidence * 100).toFixed(1)}%` : '--'}</td>
            <td><span class="badge badge--gray" style="font-size:11px">${violation.violation_type || 'red_light'}</span></td>
            <td><a href="/violation-detail?id=${violation.id}" class="btn btn--outline btn--sm">Chi tiết</a></td>
        </tr>
    `).join('');

    renderPagination(data.length);
}

function renderViolationsError(error) {
    const tbody = document.getElementById('violTableBody');
    tbody.innerHTML = `<tr><td colspan="8"><div class="alert alert--error">Lỗi: ${error.message}</div></td></tr>`;
}

function renderPagination(count) {
    const bar = document.getElementById('paginationBar');
    const hasPrev = currentPage > 1;
    const hasNext = count === LIMIT;
    bar.innerHTML = `
        <button class="page-btn" ${!hasPrev ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">< Trước</button>
        <span class="page-btn page-btn--active">Trang ${currentPage}</span>
        <button class="page-btn" ${!hasNext ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">Sau ></button>
    `;
}

function changePage(page) {
    currentPage = page;
    if (window.liveDataHub) {
        window.liveDataHub.requestSync({ resources: ['violations'], reason: 'pagination' });
    } else {
        loadViolationsFallback();
    }
    window.scrollTo(0, 0);
}
