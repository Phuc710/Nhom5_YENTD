let knownViolations = new Set();

document.addEventListener('DOMContentLoaded', () => {
    // Priority 1: Use LiveDataHub if available
    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: 'dashboard-summary',
            resources: ['summary'],
            intervalVisible: 15_000,
            intervalHidden: 60_000,
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

        window.liveDataHub.register({
            id: 'dashboard-violations',
            resources: ['violations'],
            intervalVisible: 5_000,
            intervalHidden: 30_000,
            run: () => api.getDashboardRecentViolations(10, { requestKey: 'dashboard-violations' }),
            onData: renderRecentViolations,
        });
        return;
    }

    // Fallback if LiveDataHub fails to load
    refreshDashboardFallback();
    setInterval(refreshDashboardFallback, 10000);
});

async function refreshDashboardFallback() {
    try {
        const [summary, cameras, violations] = await Promise.all([
            api.getDashboardOverview(),
            api.getDashboardCameras(),
            api.getDashboardRecentViolations(10)
        ]);
        renderSummary(summary);
        renderCameras(cameras);
        renderRecentViolations(violations);
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

function renderRecentViolations(violations) {
    const container = document.getElementById('recentActivity');
    if (!container) return;

    if (!violations.length) {
        container.innerHTML = '<div style="padding: 40px 20px; text-align: center;" class="text-muted">Chưa có vi phạm nào.</div>';
        return;
    }

    // New violation toast logic
    violations.forEach(v => {
        if (knownViolations.size > 0 && !knownViolations.has(v.id)) {
            window.ui?.toast(`Phát hiện BSX: ${v.license_plate || '---'} tại ${v.camera_name || v.camera_id}`, 'info');
        }
        knownViolations.add(v.id);
    });

    container.innerHTML = violations.map(v => `
        <div class="activity-item" onclick="location.href='/violation-detail?id=${v.id}'">
            <img src="${v.cropped_plate_url || v.full_image_url}" class="activity-thumb">
            <div class="activity-info">
                <div class="activity-plate">${v.license_plate || '---'}</div>
                <div class="activity-meta">${v.camera_name || v.camera_id} · ${formatTimeRange(v.timestamp)}</div>
            </div>
        </div>
    `).join('');
}

function formatTimeRange(iso) {
    const diff = Date.now() - new Date(iso).getTime();
    if (diff < 60000) return 'Vừa mới';
    if (diff < 3600000) return Math.floor(diff / 60000) + ' phút trước';
    return formatDateVN(iso);
}

function renderCameraError(error) {
    const grid = document.getElementById('cameraGrid');
    if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; padding:20px; color:var(--color-error); text-align:center;">Lỗi: ${error.message}</div>`;
}
