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
                <span class="card__title">Ảnh hiện trường</span>
                <a id="dFullImgLink" href="#" target="_blank" class="btn btn--outline btn--sm">Download</a>
            </div>
            <div class="card__body" style="padding:0; background: #000;">
                <img id="dFullImg" src="" style="width:100%; aspect-ratio: 16/9; object-fit: contain;">
            </div>
        </div>

        <div class="card" style="margin-top: 24px;">
            <div class="card__header"><span class="card__title">Cận cảnh biển số</span></div>
            <div class="card__body" style="background: #050505; text-align: center;">
                <img id="dCropImg" src="" style="max-height: 120px; border: 1px solid #333; padding: 4px;">
            </div>
        </div>
    </div>

    <aside class="detail-sidebar">
        <div class="card">
            <div class="card__header"><span class="card__title">Thông số hồ sơ</span></div>
            <div class="card__body">
                <div class="info-list">
                    <div class="info-row"><span class="info-label">Biển số</span><span class="info-value" id="dPlate">--</span></div>
                    <div class="info-row"><span class="info-label">Ngày giờ</span><span class="info-value" id="dTime">--</span></div>
                    <div class="info-row"><span class="info-label">Tin cậy</span><span class="info-value text-primary" id="dConfidence">--</span></div>
                    <div class="info-row" style="margin-top: 24px;"><span class="info-label">Camera</span><span class="info-value" id="dCamName">--</span></div>
                    <div class="info-row"><span class="info-label">Vị trí</span><span class="info-value" id="dCamLoc">--</span></div>
                </div>
                <a class="btn btn--outline" id="dMap" href="#" target="_blank" style="width:100%; margin-top:20px;">Google Maps</a>
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
.info-list { display: flex; flex-direction: column; gap: 12px; }
.info-row { display: flex; justify-content: space-between; font-size: 0.85rem; }
.info-label { color: var(--color-text-dim); }
.info-value { font-weight: 700; color: #fff; }
</style>

<script>
    document.addEventListener('DOMContentLoaded', async () => {
        const id = window.APP_CONFIG.VIOLATION_ID;
        try {
            const v = await api.getViolation(id);
            document.getElementById('dPlate').textContent = v.license_plate;
            document.getElementById('dPlateDisplay').textContent = v.license_plate;
            document.getElementById('dTime').textContent = formatDateVN(v.timestamp);
            document.getElementById('dConfidence').textContent = (v.confidence * 100).toFixed(1) + '%';
            document.getElementById('dCamName').textContent = v.camera_name || '--';
            document.getElementById('dCamLoc').textContent = v.location || '--';
            document.getElementById('dFullImg').src = v.full_image_url;
            document.getElementById('dFullImgLink').href = v.full_image_url;
            document.getElementById('dCropImg').src = v.cropped_plate_url || v.full_image_url;
            document.getElementById('dMap').href = `https://www.google.com/maps?q=${v.latitude},${v.longitude}`;
        } catch (e) { console.error(e); }
    });
</script>

<?php include __DIR__ . '/../includes/footer.php'; ?>