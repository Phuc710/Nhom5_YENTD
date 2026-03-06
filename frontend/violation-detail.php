<?php
require_once __DIR__ . '/config.php';

$id = (int) ($_GET['id'] ?? 0);
if ($id <= 0) {
    header('Location: /violations.php');
    exit;
}

$pageTitle = 'Chi tiết Vi phạm';
$activePage = 'violations';
$extraCss = ['/assets/css/violations.css', '/assets/css/camera.css'];
include __DIR__ . '/includes/header.php';
?>

<div style="margin-bottom:16px">
    <a href="javascript:history.back()"
        style="font-size:13px;color:var(--color-text-muted);display:inline-flex;align-items:center;gap:4px">
        <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd"
                d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
                clip-rule="evenodd" />
        </svg>
        Quay lại
    </a>
</div>

<div id="loadingState" class="loading">Đang tải chi tiết...</div>
<div id="errorState" class="alert alert--error hidden"></div>

<div id="detailWrap" class="hidden">
    <div class="page-header" style="margin-bottom:16px">
        <div>
            <h1 class="page-header__title" id="dTitle">Vi phạm #
                <?= $id ?>
            </h1>
            <p class="page-header__subtitle" id="dSubtitle">—</p>
        </div>
        <div style="text-align:right">
            <div id="dPlateDisplay" class="plate-display">—</div>
            <div class="plate-confidence" id="dConf">—</div>
        </div>
    </div>

    <div class="violation-detail">
        <!-- Left: images -->
        <div>
            <!-- Full frame -->
            <div class="card" style="margin-bottom:16px">
                <div class="card__header">
                    <span class="card__title">Ảnh vi phạm (full frame)</span>
                    <a id="dFullImgLink" href="#" target="_blank" class="btn btn--outline btn--sm">Xem gốc</a>
                </div>
                <div class="card__body" style="padding:0;position:relative">
                    <div class="violation-img-wrap" id="imgWrap">
                        <img id="dFullImg" src="" alt="Full frame">
                        <!-- Bounding box sẽ được inject vào đây bằng JS -->
                    </div>
                </div>
            </div>

            <!-- Cropped plate -->
            <div class="card" id="plateCard">
                <div class="card__header">
                    <span class="card__title">Ảnh biển số (crop)</span>
                </div>
                <div class="card__body" style="padding:0">
                    <div class="plate-img-wrap">
                        <img id="dCropImg" src="" alt="Biển số">
                    </div>
                </div>
            </div>
        </div>

        <!-- Right: info sidebar -->
        <div>
            <div class="card">
                <div class="card__header">
                    <span class="card__title">Thông tin vi phạm</span>
                </div>
                <ul class="detail-list">
                    <li>
                        <span class="detail-list__key">Biển số</span>
                        <span class="detail-list__val" id="dPlate">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Trạng thái đèn</span>
                        <span class="detail-list__val" id="dLight">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Loại vi phạm</span>
                        <span class="detail-list__val" id="dType">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Thời gian</span>
                        <span class="detail-list__val" id="dTime">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Camera</span>
                        <span class="detail-list__val" id="dCamera">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Vị trí</span>
                        <span class="detail-list__val" id="dLocation">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Confidence</span>
                        <span class="detail-list__val" id="dConfidence">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Vote</span>
                        <span class="detail-list__val" id="dVote">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Chất lượng ảnh</span>
                        <span class="detail-list__val" id="dQuality">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Thời gian xử lý</span>
                        <span class="detail-list__val" id="dProc">—</span>
                    </li>
                </ul>
            </div>

            <!-- Camera info -->
            <div class="card" style="margin-top:16px">
                <div class="card__header">
                    <span class="card__title">Camera</span>
                    <a id="dCameraLink" href="#" class="btn btn--outline btn--sm">Xem camera</a>
                </div>
                <ul class="detail-list">
                    <li><span class="detail-list__key">Tên</span><span class="detail-list__val" id="dCamName">—</span>
                    </li>
                    <li><span class="detail-list__key">Vị trí</span><span class="detail-list__val" id="dCamLoc">—</span>
                    </li>
                    <li>
                        <span class="detail-list__key">Bản đồ</span>
                        <span class="detail-list__val">
                            <a class="map-link" id="dMap" href="#" target="_blank">
                                <svg viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd"
                                        d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" />
                                </svg>
                                Xem Google Maps
                            </a>
                        </span>
                    </li>
                </ul>
            </div>
        </div>
    </div>
</div>

<script>
    window.APP_CONFIG = { API_URL: '<?= API_URL ?>', VIOLATION_ID: <?= $id ?> };

    document.addEventListener('DOMContentLoaded', async () => {
        const id = window.APP_CONFIG.VIOLATION_ID;
        const loading = document.getElementById('loadingState');
        const errEl = document.getElementById('errorState');
        const detail = document.getElementById('detailWrap');
        try {
            const v = await api.getViolation(id);
            loading.classList.add('hidden');
            detail.classList.remove('hidden');
            renderDetail(v);
        } catch (e) {
            loading.classList.add('hidden');
            errEl.classList.remove('hidden');
            errEl.textContent = 'Không tìm thấy vi phạm: ' + e.message;
        }
    });

    function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val ?? '—'; }

    function renderDetail(v) {
        document.title = `Vi phạm #${v.id} — ${v.license_plate || '?'}`;

        // Plate display
        const plate = v.license_plate || '???-???';
        document.getElementById('dPlateDisplay').textContent = plate;
        document.getElementById('dConf').textContent =
            v.confidence ? `Confidence: ${(v.confidence * 100).toFixed(1)}%` : '';

        setText('dTitle', `Vi phạm #${v.id}`);
        setText('dSubtitle', `${v.camera_name || v.camera_id} · ${formatDateVN(v.timestamp)}`);
        document.getElementById('dPlate').innerHTML = plateBadge(v.license_plate);
        document.getElementById('dLight').innerHTML = lightBadge(v.traffic_light_state);
        setText('dType', v.violation_type || 'red_light');
        setText('dTime', formatDateVN(v.timestamp));
        setText('dCamera', `Cam #${v.camera_id}`);
        setText('dLocation', v.location || '—');
        setText('dConfidence', v.confidence ? (v.confidence * 100).toFixed(2) + '%' : '—');
        setText('dVote', v.vote_count && v.total_frames
            ? `${v.vote_count}/${v.total_frames} (${v.vote_percent?.toFixed(1)}%)`
            : '—');
        setText('dQuality', v.image_quality_score ? v.image_quality_score.toFixed(1) + '/100' : '—');
        setText('dProc', v.processing_time_ms ? v.processing_time_ms + 'ms' : '—');

        // Camera link
        setText('dCamName', v.camera_name || '—');
        setText('dCamLoc', v.location || '—');
        const camLink = document.getElementById('dCameraLink');
        camLink.href = `/camera.php?id=${v.camera_id}`;

        if (v.latitude && v.longitude) {
            document.getElementById('dMap').href = `https://www.google.com/maps?q=${v.latitude},${v.longitude}`;
        }

        // Full image + bbox
        const img = document.getElementById('dFullImg');
        img.src = v.full_image_url || '';
        document.getElementById('dFullImgLink').href = v.full_image_url || '#';

        if (v.bbox_x != null && v.bbox_y != null && v.bbox_w && v.bbox_h) {
            img.addEventListener('load', () => {
                injectBbox(v, img);
            }, { once: true });
            if (img.complete && img.naturalWidth) injectBbox(v, img);
        }

        // Cropped plate
        if (v.cropped_plate_url) {
            document.getElementById('dCropImg').src = v.cropped_plate_url;
        } else {
            document.getElementById('plateCard').classList.add('hidden');
        }
    }

    function injectBbox(v, img) {
        const wrap = document.getElementById('imgWrap');
        const scaleX = img.clientWidth / (img.naturalWidth || img.clientWidth);
        const scaleY = img.clientHeight / (img.naturalHeight || img.clientHeight);

        const box = document.createElement('div');
        box.className = 'violation-bbox';
        Object.assign(box.style, {
            left: (v.bbox_x * scaleX) + 'px',
            top: (v.bbox_y * scaleY) + 'px',
            width: (v.bbox_w * scaleX) + 'px',
            height: (v.bbox_h * scaleY) + 'px',
        });
        const lbl = document.createElement('div');
        lbl.className = 'violation-bbox__label';
        lbl.textContent = v.license_plate || 'Xe vi phạm';
        box.appendChild(lbl);
        wrap.appendChild(box);
    }
</script>

<?php include __DIR__ . '/includes/footer.php'; ?>