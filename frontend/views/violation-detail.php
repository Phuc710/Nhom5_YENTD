<?php
use Frontend\App\Core\Page;

$violationId = $id ?? 0;

$page = new Page(
    title: "Vi phạm #$violationId",
    activePage: 'violations',
    extraCss: ['/assets/css/pages/camera-detail.css'],
    appConfig: ['VIOLATION_ID' => $violationId]
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px; display: flex; justify-content: space-between; align-items: center;">
    <div>
        <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase;">Chi tiết vi phạm</h1>
        <p class="text-muted">Hồ sơ #<?= $violationId ?> được ghi lại từ camera AI.</p>
    </div>
    <div id="dPlateDisplay" class="plate-badge" style="font-size: 2rem; padding: 12px 24px;">---</div>
</div>

<div class="detail-layout">
    <div class="detail-main">
        <div class="card">
            <div class="card__header">
                <span class="card__title">Ảnh bằng chứng (Snapshot)</span>
                <a id="dFullImgLink" href="#" target="_blank" class="btn btn--outline btn--sm">Tải ảnh gốc</a>
            </div>
            <div class="card__body" style="padding:0; background: #000; position: relative;">
                <img id="dFullImg" src="" style="width:100%; aspect-ratio: 16/9; object-fit: contain;">
                <div id="dCaptureLabel"
                    style="position:absolute; bottom:12px; left:12px; background:rgba(0,0,0,0.6); color:#fff; padding:4px 10px; border-radius:4px; font-size:0.75rem;">
                    Ảnh chụp lúc cắt vạch</div>
            </div>
        </div>

        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px; margin-top:24px;">
            <div class="card">
                <div class="card__header"><span class="card__title">Cận cảnh phương tiện</span></div>
                <div class="card__body" style="background: #050505; text-align: center; padding:12px;">
                    <img id="dVehicleImg" src=""
                        style="width:100%; aspect-ratio:4/3; object-fit: cover; border: 1px solid #222;">
                </div>
            </div>
            <div class="card">
                <div class="card__header"><span class="card__title">Cận cảnh biển số</span></div>
                <div class="card__body" style="background: #050505; text-align: center; padding:12px;">
                    <img id="dCropImg" src=""
                        style="width:100%; aspect-ratio:4/3; object-fit: contain; border: 1px solid #222; background:#111;">
                </div>
            </div>
        </div>
    </div>

    <aside class="detail-sidebar">
        <div class="card">
            <div class="card__header"><span class="card__title">Thông số hồ sơ</span></div>
            <div class="card__body">
                <div class="info-list">
                    <div class="info-row"><span class="info-label">Biển số</span><span class="info-value"
                            id="dPlate">--</span></div>
                    <div class="info-row"><span class="info-label">Ngày giờ</span><span class="info-value"
                            id="dTime">--</span></div>
                    <div class="info-row"><span class="info-label">Tin cậy</span><span class="info-value text-primary"
                            id="dConfidence">--</span></div>
                    <div class="info-row" style="margin-top: 24px;"><span class="info-label">Camera</span><span
                            class="info-value" id="dCamName">--</span></div>
                    <div class="info-row"><span class="info-label">Vị trí</span><span class="info-value"
                            id="dCamLoc">--</span></div>
                </div>
                <a class="btn btn--outline" id="dMap" href="#" target="_blank"
                    style="width:100%; margin-top:20px;">Google Maps</a>
            </div>
        </div>
    </aside>
</div>

<style>
    .plate-badge {
        background: #111;
        color: #fff;
        border: 1px solid #333;
        font-family: monospace;
        font-weight: 800;
    }

    .info-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .info-row {
        display: flex;
        justify-content: space-between;
        font-size: 0.85rem;
    }

    .info-label {
        color: var(--color-text-dim);
    }

    .info-value {
        font-weight: 700;
        color: #fff;
    }
</style>

<script>
    document.addEventListener('DOMContentLoaded', async () => {
        const id = window.APP_CONFIG.VIOLATION_ID;
        try {
            const v = await api.getViolation(id);
            document.getElementById('dPlate').textContent = v.license_plate || 'KHÔNG RÕ';
            document.getElementById('dPlateDisplay').textContent = v.license_plate || '---';
            document.getElementById('dTime').textContent = formatDateVN(v.timestamp);
            document.getElementById('dConfidence').textContent = v.confidence ? (v.confidence * 100).toFixed(1) + '%' : '--';
            document.getElementById('dCamName').textContent = v.camera_name || '--';
            document.getElementById('dCamLoc').textContent = v.location || '--';

            const mainImg = v.stop_line_snapshot_url || v.full_image_url;
            document.getElementById('dFullImg').src = mainImg;
            document.getElementById('dFullImgLink').href = mainImg;

            document.getElementById('dVehicleImg').src = v.cropped_vehicle_url || v.full_image_url;
            document.getElementById('dCropImg').src = v.cropped_plate_url || v.full_image_url;

            document.getElementById('dMap').href = `https://www.google.com/maps?q=${v.latitude || 0},${v.longitude || 0}`;
        } catch (e) { console.error(e); }
    });
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>