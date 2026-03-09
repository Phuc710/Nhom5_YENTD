document.addEventListener('DOMContentLoaded', () => {
    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: 'dashboard-summary',
            resources: ['summary', 'cameras', 'violations'],
            intervalVisible: 15_000,
            intervalHidden: 90_000,
            run: () => api.getDashboardOverview({ requestKey: 'dashboard-summary' }),
            onData: renderSummary,
        });

        window.liveDataHub.register({
            id: 'dashboard-cameras',
            resources: ['summary', 'cameras'],
            intervalVisible: 20_000,
            intervalHidden: 90_000,
            run: () => api.getDashboardCameras({ requestKey: 'dashboard-cameras' }),
            onData: renderCameras,
            onError: renderCameraError,
        });

        window.liveDataHub.register({
            id: 'dashboard-violations',
            resources: ['summary', 'violations'],
            intervalVisible: 12_000,
            intervalHidden: 90_000,
            run: () => api.getDashboardRecentViolations(10, { requestKey: 'dashboard-violations' }),
            onData: renderRecent,
            onError: renderRecentError,
        });
        return;
    }

    refreshDashboardFallback();
    setInterval(refreshDashboardFallback, 30_000);
});

async function refreshDashboardFallback() {
    try {
        renderSummary(await api.getDashboardOverview());
        renderCameras(await api.getDashboardCameras());
        renderRecent(await api.getDashboardRecentViolations(10));
    } catch (error) {
        console.error('Dashboard fallback refresh:', error);
    }
}

function renderSummary(summary) {
    document.getElementById('statToday').textContent = summary.violations_today ?? 0;
    document.getElementById('statOnline').textContent = summary.online_cameras ?? 0;
    document.getElementById('statTotal').textContent = `/ ${summary.total_cameras ?? 0} camera`;
    document.getElementById('statAll').textContent = summary.violations_total ?? 0;
}

function renderCameras(cameras) {
    const grid = document.getElementById('cameraGrid');
    if (!cameras.length) {
        grid.innerHTML = '<p class="empty-state">Chua co camera nao.</p>';
        return;
    }
    grid.innerHTML = cameras.map((camera) => renderCameraCard(camera)).join('');
}

function renderCameraError(error) {
    const grid = document.getElementById('cameraGrid');
    grid.innerHTML = `<div class="alert alert--error">Loi tai danh sach camera: ${error.message}</div>`;
}

function renderRecent(violations) {
    const tbody = document.getElementById('recentTableBody');
    if (!violations.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state" style="padding:32px;text-align:center">Chua co vi pham.</td></tr>';
        return;
    }

    tbody.innerHTML = violations.map((violation) => `
        <tr>
            <td>${violation.full_image_url ? `<img class="thumb" src="${violation.full_image_url}" alt="">` : '--'}</td>
            <td>${plateBadge(violation.license_plate)}</td>
            <td>${violation.camera_name || violation.camera_id}</td>
            <td>${formatDateVN(violation.timestamp)}</td>
            <td>${lightBadge(violation.traffic_light_state)}</td>
            <td>${violation.confidence ? `${(violation.confidence * 100).toFixed(1)}%` : '--'}</td>
            <td><a href="/violation-detail.php?id=${violation.id}" class="btn btn--outline btn--sm">Chi tiet</a></td>
        </tr>
    `).join('');
}

function renderRecentError(error) {
    const tbody = document.getElementById('recentTableBody');
    tbody.innerHTML = `<tr><td colspan="7" class="alert alert--error">Loi tai vi pham: ${error.message}</td></tr>`;
}
