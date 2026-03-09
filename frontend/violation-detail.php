<?php
require_once __DIR__ . '/bootstrap.php';

use Frontend\App\Core\Page;

$id = (int) ($_GET['id'] ?? 0);
if ($id <= 0) {
    header('Location: /violations.php');
    exit;
}

$page = new Page(
    title: 'Chi tiết vi phạm',
    activePage: 'violations',
    extraCss: ['/assets/css/violations.css', '/assets/css/camera.css'],
    appConfig: ['VIOLATION_ID' => $id],
    section: 'admin',
);

include __DIR__ . '/includes/header.php';
?>

<div style="margin-bottom:16px">
    <a href="javascript:history.back()" class="btn btn--outline btn--sm">← Quay lại</a>
</div>

<div id="loadingState" class="loading">Đang tải chi tiết...</div>
<div id="errorState" class="alert alert--error hidden"></div>

<div id="detailWrap" class="hidden">
    <div class="page-header" style="margin-bottom:16px">
        <div>
            <h1 class="page-header__title" id="dTitle">Vi phạm #<?= $id ?></h1>
            <p class="page-header__subtitle" id="dSubtitle">—</p>
        </div>
        <div style="text-align:right">
            <div id="dPlateDisplay" class="plate-display">—</div>
            <div class="plate-confidence" id="dConf">—</div>
        </div>
    </div>

    <div class="violation-detail">
        <div>
            <div class="card" style="margin-bottom:16px">
                <div class="card__header">
                    <span class="card__title">Ảnh vi phạm</span>
                    <a id="dFullImgLink" href="#" target="_blank" class="btn btn--outline btn--sm">Xem ảnh gốc</a>
                </div>
                <div class="card__body" style="padding:0;position:relative">
                    <div class="violation-img-wrap" id="imgWrap">
                        <img id="dFullImg" src="" alt="Full frame">
                    </div>
                </div>
            </div>

            <div class="card" id="plateCard">
                <div class="card__header">
                    <span class="card__title">Ảnh crop biển số</span>
                </div>
                <div class="card__body" style="padding:0">
                    <div class="plate-img-wrap">
                        <img id="dCropImg" src="" alt="Biển số">
                    </div>
                </div>
            </div>
        </div>

        <div>
            <div class="card">
                <div class="card__header">
                    <span class="card__title">Thông tin vi phạm</span>
                </div>
                <ul class="detail-list">
                    <li><span class="detail-list__key">Biển số</span><span class="detail-list__val" id="dPlate">—</span></li>
                    <li><span class="detail-list__key">Trạng thái đèn</span><span class="detail-list__val" id="dLight">—</span></li>
                    <li><span class="detail-list__key">Loại vi phạm</span><span class="detail-list__val" id="dType">—</span></li>
                    <li><span class="detail-list__key">Ngày giờ</span><span class="detail-list__val" id="dTime">—</span></li>
                    <li><span class="detail-list__key">Camera</span><span class="detail-list__val" id="dCamera">—</span></li>
                    <li><span class="detail-list__key">Vị trí</span><span class="detail-list__val" id="dLocation">—</span></li>
                    <li><span class="detail-list__key">Confidence</span><span class="detail-list__val" id="dConfidence">—</span></li>
                    <li><span class="detail-list__key">Vote</span><span class="detail-list__val" id="dVote">—</span></li>
                    <li><span class="detail-list__key">Chất lượng ảnh</span><span class="detail-list__val" id="dQuality">—</span></li>
                    <li><span class="detail-list__key">Thời gian xử lý</span><span class="detail-list__val" id="dProc">—</span></li>
                </ul>
            </div>

            <div class="card" style="margin-top:16px">
                <div class="card__header">
                    <span class="card__title">Thông tin camera</span>
                    <a id="dCameraLink" href="#" class="btn btn--outline btn--sm">Xem camera</a>
                </div>
                <ul class="detail-list">
                    <li><span class="detail-list__key">Tên</span><span class="detail-list__val" id="dCamName">—</span></li>
                    <li><span class="detail-list__key">Vị trí</span><span class="detail-list__val" id="dCamLoc">—</span></li>
                    <li><span class="detail-list__key">Bản đồ</span><span class="detail-list__val"><a class="map-link" id="dMap" href="#" target="_blank">Xem Google Maps</a></span></li>
                </ul>
            </div>
        </div>
    </div>
</div>

<?= $page->configScript() ?>

<script>
    document.addEventListener('DOMContentLoaded', async () => {
        const id = window.APP_CONFIG.VIOLATION_ID;
        const loading = document.getElementById('loadingState');
        const errEl = document.getElementById('errorState');
        const detail = document.getElementById('detailWrap');
        try {
            const violation = await api.getViolation(id);
            loading.classList.add('hidden');
            detail.classList.remove('hidden');
            renderViolationDetail(violation);
        } catch (error) {
            loading.classList.add('hidden');
            errEl.classList.remove('hidden');
            errEl.textContent = `Không tìm thấy vi phạm: ${error.message}`;
        }
    });
</script>

<?php include __DIR__ . '/includes/footer.php'; ?>
