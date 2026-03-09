let currentPage = 1;
const LIMIT = 20;
let currentFilters = {};

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

function applyFilter() {
    currentPage = 1;
    currentFilters = {
        camera_id: document.getElementById('fCamera').value || null,
        license_plate: document.getElementById('fPlate').value.trim() || null,
        date_from: document.getElementById('fFrom').value || null,
        date_to: document.getElementById('fTo').value || null,
    };

    if (window.liveDataHub) {
        window.liveDataHub.requestSync({ resources: ['violations'], reason: 'filter-change' });
        return;
    }

    loadViolationsFallback();
}

function resetFilter() {
    document.getElementById('fCamera').value = '';
    document.getElementById('fPlate').value = '';
    document.getElementById('fFrom').value = '';
    document.getElementById('fTo').value = '';
    currentFilters = {};
    currentPage = 1;

    if (window.liveDataHub) {
        window.liveDataHub.requestSync({ resources: ['violations'], reason: 'filter-reset' });
        return;
    }

    loadViolationsFallback();
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
    document.getElementById('totalBadge').textContent = `${data.length} ket qua`;

    if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="8"><div class="empty-state" style="padding:40px">Khong co vi pham nao</div></td></tr>';
        renderPagination(0);
        return;
    }

    tbody.innerHTML = data.map((violation) => `
        <tr>
            <td>${violation.full_image_url ? `<img class="thumb" src="${violation.full_image_url}" alt="">` : '--'}</td>
            <td>${plateBadge(violation.license_plate)}</td>
            <td>
                <a href="/camera.php?id=${violation.camera_id}" style="font-weight:600;font-size:13px;">${violation.camera_name || violation.camera_id}</a>
                <div style="font-size:11px;color:#9CA3AF;margin-top:2px">${violation.location || ''}</div>
            </td>
            <td style="font-size:12px;white-space:nowrap">${formatDateVN(violation.timestamp)}</td>
            <td>${lightBadge(violation.traffic_light_state)}</td>
            <td style="font-size:12px">${violation.confidence ? `${(violation.confidence * 100).toFixed(1)}%` : '--'}</td>
            <td><span class="badge badge--gray" style="font-size:11px">${violation.violation_type || 'red_light'}</span></td>
            <td><a href="/violation-detail.php?id=${violation.id}" class="btn btn--outline btn--sm">Chi tiet</a></td>
        </tr>
    `).join('');

    renderPagination(data.length);
}

function renderViolationsError(error) {
    const tbody = document.getElementById('violTableBody');
    tbody.innerHTML = `<tr><td colspan="8"><div class="alert alert--error">Loi: ${error.message}</div></td></tr>`;
}

function renderPagination(count) {
    const bar = document.getElementById('paginationBar');
    const hasPrev = currentPage > 1;
    const hasNext = count === LIMIT;
    bar.innerHTML = `
        <button class="page-btn" ${!hasPrev ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">< Truoc</button>
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
