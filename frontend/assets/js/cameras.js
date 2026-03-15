let allCameras = [];

document.addEventListener('DOMContentLoaded', () => {
    if (window.liveDataHub) {
        window.liveDataHub.register({
            id: 'camera-catalog',
            resources: ['cameras', 'summary'],
            intervalVisible: 20_000,
            intervalHidden: 90_000,
            run: () => api.getCameras({ requestKey: 'camera-catalog' }),
            onData: (cameras) => {
                allCameras = cameras;
                renderCameraStats(cameras);
                applyCameraFilter();
            },
            onError: (error) => {
                const container = document.getElementById('cameraCatalog');
                container.innerHTML = `<div class="alert alert--error">Không tải được danh sách camera: ${error.message}</div>`;
            },
        });
        return;
    }

    loadCameraCatalogFallback();
    setInterval(loadCameraCatalogFallback, 30_000);
});

async function loadCameraCatalogFallback() {
    try {
        allCameras = await api.getCameras();
        renderCameraStats(allCameras);
        applyCameraFilter();
    } catch (error) {
        const container = document.getElementById('cameraCatalog');
        container.innerHTML = `<div class="alert alert--error">Không tải được danh sách camera: ${error.message}</div>`;
    }
}

function renderCameraStats(cameras) {
    const online = cameras.filter((camera) => camera.online).length;
    document.getElementById('cameraTotal').textContent = cameras.length;
    document.getElementById('cameraOnline').textContent = online;
    document.getElementById('cameraOffline').textContent = cameras.length - online;
}

function renderCameraCatalog(cameras) {
    const container = document.getElementById('cameraCatalog');
    if (!cameras.length) {
        container.innerHTML = '<div class="empty-state">Không có camera nào phù hợp.</div>';
        return;
    }
    container.innerHTML = cameras.map(renderCameraCard).join('');
}

function applyCameraFilter() {
    const keyword = document.getElementById('cameraSearch').value.trim().toLowerCase();
    const status = document.getElementById('cameraStatus').value;

    const filtered = allCameras.filter((camera) => {
        const matchesKeyword = !keyword
            || `${camera.camera_name || ''} ${camera.location || ''}`.toLowerCase().includes(keyword);
        const matchesStatus = !status
            || (status === 'online' ? !!camera.online : !camera.online);
        return matchesKeyword && matchesStatus;
    });

    renderCameraCatalog(filtered);
    document.getElementById('cameraCountLabel').textContent = `${filtered.length} thiết bị`;
}

function resetCameraFilter() {
    document.getElementById('cameraSearch').value = '';
    document.getElementById('cameraStatus').value = '';
    renderCameraCatalog(allCameras);
    document.getElementById('cameraCountLabel').textContent = `${allCameras.length} thiết bị`;
}
