document.addEventListener('DOMContentLoaded', () => {
    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: 'dashboard-summary',
            resources: ['summary'],
            intervalVisible: 15_000,
            intervalHidden: 90_000,
            run: () => api.getDashboardOverview({ requestKey: 'dashboard-summary' }),
            onData: renderSummary,
        });

        window.liveDataHub.register({
            id: 'dashboard-cameras',
            resources: ['cameras'],
            intervalVisible: 20_000,
            intervalHidden: 90_000,
            run: () => api.getDashboardCameras({ requestKey: 'dashboard-cameras' }),
            onData: renderCameras,
            onError: renderCameraError,
        });
        return;
    }

    refreshDashboardFallback();
});

async function refreshDashboardFallback() {
    try {
        const [summary, cameras] = await Promise.all([
            api.getDashboardOverview(),
            api.getDashboardCameras()
        ]);
        renderSummary(summary);
        renderCameras(cameras);
    } catch (error) {
        console.error('Dashboard fallback refresh:', error);
    }
}

function renderSummary(summary) {
    const container = document.getElementById('statusSummary');
    if (!container) return;

    container.innerHTML = `
        <div class="badge badge--online">${summary.online_cameras || 0} Trực tuyến</div>
        <div class="badge badge--offline">${(summary.total_cameras || 0) - (summary.online_cameras || 0)} Ngoại tuyến</div>
    `;
}

function renderCameras(cameras) {
    const grid = document.getElementById('cameraGrid');
    if (!grid) return;

    if (!cameras.length) {
        grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:48px;" class="text-muted">Chưa có camera nào được cấu hình.</div>';
        return;
    }

    grid.innerHTML = cameras.map(camera => `
        <div class="card cam-card" onclick="location.href='/camera/${camera.id}'">
            <div class="cam-card__preview">
                <img src="${camera.preview_url || '/assets/img/placeholder-cam.jpg'}" alt="${camera.camera_name}">
                <div class="cam-card__status">
                    <span class="badge ${camera.state === 'online' ? 'badge--online' : 'badge--offline'}">
                        ${camera.state === 'online' ? 'ONLINE' : 'OFFLINE'}
                    </span>
                </div>
            </div>
            <div class="cam-card__body">
                <div class="cam-card__title">${camera.camera_name || `Camera #${camera.id}`}</div>
                <div class="cam-card__meta">
                    <span style="display:block; margin-bottom:4px;">📍 ${camera.location || 'Vị trí chưa xác định'}</span>
                    <span>IP: ${camera.ip_address || '--'}</span>
                </div>
            </div>
        </div>
    `).join('');
}

function renderCameraError(error) {
    const grid = document.getElementById('cameraGrid');
    if (grid) {
        grid.innerHTML = `<div style="grid-column: 1/-1; padding:20px; color:var(--color-error); text-align:center;">Lỗi tải dữ liệu: ${error.message}</div>`;
    }
}
