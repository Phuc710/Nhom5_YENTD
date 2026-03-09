<?php
require_once __DIR__ . '/bootstrap.php';

use Frontend\App\Core\Page;

$cameraId = (int) ($_GET['id'] ?? 0);
if ($cameraId <= 0) {
    header('Location: /cameras.php');
    exit;
}

$page = new Page(
    title: 'Chi tiết camera',
    activePage: 'cameras',
    extraCss: ['/assets/css/camera.css', '/assets/css/zone-editor.css', '/assets/css/violations.css'],
    extraJs: ['/assets/js/zone-editor.js', '/assets/js/camera.js'],
    appConfig: ['CAMERA_ID' => $cameraId],
    section: 'admin',
);

include __DIR__ . '/includes/header.php';
?>

<div class="page-header">
    <div>
        <a href="/cameras.php" class="btn btn--outline btn--sm" style="margin-bottom:10px;">← Danh sách camera</a>
        <h1 class="page-header__title" id="camTitle">Camera #<?= $cameraId ?></h1>
        <p class="page-header__subtitle" id="camLocation">Đang tải thông tin camera...</p>
    </div>
    <div class="inline-actions">
        <button class="btn btn--outline" onclick="openEditModal()">Sửa cấu hình</button>
        <button class="btn btn--primary" id="btnSaveZones" onclick="saveZones()">Lưu zone</button>
    </div>
</div>

<div class="camera-detail">
    <div>
        <div class="card" style="margin-bottom:16px">
            <div class="card__header">
                <span class="card__title">Stream trực tiếp</span>
                <span id="streamStatus" class="badge badge--gray">—</span>
            </div>
            <div class="card__body" style="padding:0">
                <div class="camera-stream-wrap" id="streamWrap">
                    <img id="streamImg" src="" alt="Camera stream" style="display:none"
                        onload="document.getElementById('streamStatus').textContent='Live';document.getElementById('streamStatus').className='badge badge--green';"
                        onerror="document.getElementById('streamStatus').textContent='Không có stream';document.getElementById('streamStatus').className='badge badge--gray';">
                    <div class="no-stream" id="noStream">Chưa cấu hình stream URL</div>
                </div>
            </div>
        </div>

        <div class="zone-editor-panel">
            <div class="zone-editor-panel__title">Cấu hình zone phát hiện và stop line</div>
            <div class="zone-editor-controls">
                <select class="zone-type-select" id="zoneTypeSelect" onchange="setZoneType(this.value)">
                    <option value="detection">Detection zone</option>
                    <option value="stop_line">Stop line</option>
                    <option value="roi">ROI</option>
                </select>
                <button class="btn btn--outline btn--sm" onclick="clearZones()">Xóa tất cả</button>
            </div>

            <div class="zone-info" id="zoneInfo" style="display:none">
                <div class="zone-info__item"><label>X</label><input type="number" id="ziX" onchange="updateSelectedZone()"></div>
                <div class="zone-info__item"><label>Y</label><input type="number" id="ziY" onchange="updateSelectedZone()"></div>
                <div class="zone-info__item"><label>Width</label><input type="number" id="ziW" onchange="updateSelectedZone()"></div>
                <div class="zone-info__item"><label>Height</label><input type="number" id="ziH" onchange="updateSelectedZone()"></div>
            </div>

            <div style="font-size:11px;color:var(--color-text-muted);margin-bottom:8px">Dữ liệu zone hiện tại</div>
            <pre class="zone-json-preview" id="zoneJsonPreview">[]</pre>
        </div>
    </div>

    <div>
        <div class="cam-info-card" style="margin-bottom:16px">
            <div class="cam-info-card__header">
                <span class="cam-info-card__title">Thông tin thiết bị</span>
                <span class="status-dot" id="onlineDot"></span>
            </div>
            <div class="cam-info-row"><span class="cam-info-row__label">Camera ID</span><span class="cam-info-row__value" id="infoId">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Tên</span><span class="cam-info-row__value" id="infoName">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Vị trí</span><span class="cam-info-row__value" id="infoLoc">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">IP</span><span class="cam-info-row__value" id="infoIp">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">MAC</span><span class="cam-info-row__value" id="infoMac">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Firmware</span><span class="cam-info-row__value" id="infoFw">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Lần cuối</span><span class="cam-info-row__value" id="infoSeen">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Stream URL</span><span class="cam-info-row__value" id="infoStream" style="word-break:break-all;font-size:11px">—</span></div>
            <div class="cam-info-row">
                <span class="cam-info-row__label">Bản đồ</span>
                <a class="map-link" id="infoMap" href="#" target="_blank">Xem Google Maps</a>
            </div>
        </div>

        <div class="card">
            <div class="card__header">
                <span class="card__title">Vi phạm gần nhất của camera</span>
                <a href="/violations.php?camera_id=<?= $cameraId ?>" class="btn btn--outline btn--sm">Xem tất cả</a>
            </div>
            <div class="table-container">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Ảnh</th>
                            <th>Biển số</th>
                            <th>Thời gian</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="camViolations">
                        <tr>
                            <td colspan="4" class="loading">Đang tải...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<div class="modal-overlay hidden" id="editModal">
    <div class="modal">
        <div class="modal__header">
            <span class="modal__title">Sửa cấu hình camera</span>
            <button class="modal__close" onclick="closeEditModal()">×</button>
        </div>
        <div class="modal__body">
            <div id="editAlert"></div>
            <div class="form-group">
                <label class="form-label">Tên camera</label>
                <input class="form-control" id="editName" type="text">
            </div>
            <div class="form-group">
                <label class="form-label">Vị trí</label>
                <input class="form-control" id="editLoc" type="text">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Latitude</label>
                    <input class="form-control" id="editLat" type="number" step="0.0000001">
                </div>
                <div class="form-group">
                    <label class="form-label">Longitude</label>
                    <input class="form-control" id="editLng" type="number" step="0.0000001">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Stream URL</label>
                <input class="form-control" id="editStream" type="url">
            </div>
            <div class="form-group">
                <label class="form-label">Tên thiết bị ThingsBoard</label>
                <input class="form-control" id="editTbName" type="text">
            </div>
            <div class="form-group">
                <label class="form-label">Mô tả</label>
                <textarea class="form-control" id="editDesc" rows="3"></textarea>
            </div>
            <div class="camera-danger-zone">
                <div class="camera-danger-zone__title">Factory Reset Thiết Bị</div>
                <p class="camera-danger-zone__desc">
                    Lệnh reset trên web sẽ xóa toàn bộ NVS của ESP32 rồi khởi động lại.
                </p>
                <div id="factoryResetAlert"></div>
                <button class="btn btn--danger" id="btnFactoryReset" onclick="factoryResetCamera()">
                    Factory reset thiết bị
                </button>
            </div>
        </div>
        <div class="modal__footer">
            <button class="btn btn--outline" onclick="closeEditModal()">Hủy</button>
            <button class="btn btn--primary" onclick="saveConfig()">Lưu thay đổi</button>
        </div>
    </div>
</div>

<?= $page->configScript() ?>

<?php include __DIR__ . '/includes/footer.php'; ?>
