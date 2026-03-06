<?php
require_once __DIR__ . '/config.php';

$cameraId = (int) ($_GET['id'] ?? 0);
if ($cameraId <= 0) {
    header('Location: /index.php');
    exit;
}

$pageTitle = 'Chi tiết Camera';
$activePage = 'dashboard';
$extraCss = ['/assets/css/camera.css', '/assets/css/zone-editor.css', '/assets/css/violations.css'];
$extraJs = ['/assets/js/zone-editor.js', '/assets/js/camera.js'];

include __DIR__ . '/includes/header.php';
?>

<div class="page-header">
    <div>
        <a href="/index.php"
            style="font-size:13px;color:var(--color-text-muted);display:flex;align-items:center;gap:4px;margin-bottom:6px">
            <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd"
                    d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
                    clip-rule="evenodd" />
            </svg>
            Dashboard
        </a>
        <h1 class="page-header__title" id="camTitle">Camera #
            <?= $cameraId ?>
        </h1>
        <p class="page-header__subtitle" id="camLocation">Đang tải...</p>
    </div>
    <div style="display:flex;gap:8px">
        <button class="btn btn--outline" onclick="openEditModal()">
            <svg viewBox="0 0 20 20" fill="currentColor">
                <path
                    d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
            </svg>
            Sửa cấu hình
        </button>
        <button class="btn btn--primary" id="btnSaveZones" onclick="saveZones()">
            <svg viewBox="0 0 20 20" fill="currentColor">
                <path
                    d="M7.707 10.293a1 1 0 10-1.414 1.414l3 3a1 1 0 001.414 0l3-3a1 1 0 00-1.414-1.414L11 11.586V6h5a2 2 0 012 2v7a2 2 0 01-2 2H4a2 2 0 01-2-2V8a2 2 0 012-2h5v5.586l-1.293-1.293z" />
            </svg>
            Lưu Zones
        </button>
    </div>
</div>

<div class="camera-detail">
    <!-- Left: stream + zone editor -->
    <div>
        <div class="card" style="margin-bottom:16px">
            <div class="card__header">
                <span class="card__title">Live Stream</span>
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

        <!-- Zone controls -->
        <div class="zone-editor-panel">
            <div class="zone-editor-panel__title">
                <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
                    <path
                        d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM14 11a1 1 0 011 1v1h1a1 1 0 110 2h-1v1a1 1 0 11-2 0v-1h-1a1 1 0 110-2h1v-1a1 1 0 011-1z" />
                </svg>
                Vùng phát hiện (Zones)
            </div>
            <div class="zone-editor-controls">
                <select class="zone-type-select" id="zoneTypeSelect" onchange="setZoneType(this.value)">
                    <option value="detection">🟢 Detection</option>
                    <option value="stop_line">🟡 Stop Line</option>
                    <option value="roi">🔵 ROI</option>
                </select>
                <button class="btn btn--outline btn--sm" onclick="clearZones()">Xóa tất cả</button>
            </div>

            <!-- Selected zone info -->
            <div class="zone-info" id="zoneInfo" style="display:none">
                <div class="zone-info__item">
                    <label>X</label><input type="number" id="ziX" onchange="updateSelectedZone()">
                </div>
                <div class="zone-info__item">
                    <label>Y</label><input type="number" id="ziY" onchange="updateSelectedZone()">
                </div>
                <div class="zone-info__item">
                    <label>Width</label><input type="number" id="ziW" onchange="updateSelectedZone()">
                </div>
                <div class="zone-info__item">
                    <label>Height</label><input type="number" id="ziH" onchange="updateSelectedZone()">
                </div>
            </div>

            <div style="font-size:11px;color:var(--color-text-muted);margin-bottom:8px">JSON zones</div>
            <pre class="zone-json-preview" id="zoneJsonPreview">[]</pre>
        </div>
    </div>

    <!-- Right: camera info + recent violations -->
    <div>
        <!-- Camera info -->
        <div class="cam-info-card" style="margin-bottom:16px">
            <div class="cam-info-card__header">
                <span class="cam-info-card__title">Thông tin thiết bị</span>
                <span class="status-dot" id="onlineDot"></span>
            </div>
            <div class="cam-info-row"><span class="cam-info-row__label">Camera ID</span><span
                    class="cam-info-row__value" id="infoId">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Tên</span><span class="cam-info-row__value"
                    id="infoName">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Vị trí</span><span class="cam-info-row__value"
                    id="infoLoc">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">IP</span><span class="cam-info-row__value"
                    id="infoIp">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">MAC</span><span class="cam-info-row__value"
                    id="infoMac">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Firmware</span><span class="cam-info-row__value"
                    id="infoFw">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Lần cuối</span><span class="cam-info-row__value"
                    id="infoSeen">—</span></div>
            <div class="cam-info-row"><span class="cam-info-row__label">Stream URL</span><span
                    class="cam-info-row__value" id="infoStream" style="word-break:break-all;font-size:11px">—</span>
            </div>
            <div class="cam-info-row">
                <span class="cam-info-row__label">Bản đồ</span>
                <a class="map-link" id="infoMap" href="#" target="_blank">
                    <svg viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd"
                            d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" />
                    </svg>
                    Xem
                </a>
            </div>
        </div>

        <!-- Recent violations for this camera -->
        <div class="card">
            <div class="card__header">
                <span class="card__title">Vi phạm gần nhất</span>
                <a href="/violations.php?camera_id=<?= $cameraId ?>" class="btn btn--outline btn--sm">Xem tất cả</a>
            </div>
            <div class="table-container">
                <table class="table">
                    <thead>
                        <tr>
                            <th>Ảnh</th>
                            <th>BSX</th>
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

<!-- Edit Config Modal -->
<div class="modal-overlay hidden" id="editModal">
    <div class="modal">
        <div class="modal__header">
            <span class="modal__title">Sửa cấu hình Camera</span>
            <button class="modal__close" onclick="closeEditModal()">✕</button>
        </div>
        <div class="modal__body">
            <div id="editAlert"></div>
            <div class="form-group">
                <label class="form-label">Tên camera</label>
                <input class="form-control" id="editName" type="text" placeholder="VD: Camera Gò Vấp">
            </div>
            <div class="form-group">
                <label class="form-label">Vị trí</label>
                <input class="form-control" id="editLoc" type="text"
                    placeholder="VD: Ngã tư Phan Văn Trị - Quang Trung">
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
                <label class="form-label">Stream URL (ESP32)</label>
                <input class="form-control" id="editStream" type="url" placeholder="http://192.168.1.100/stream">
            </div>
            <div class="form-group">
                <label class="form-label">Tên thiết bị ThingsBoard</label>
                <input class="form-control" id="editTbName" type="text">
            </div>
            <div class="form-group">
                <label class="form-label">Mô tả</label>
                <textarea class="form-control" id="editDesc" rows="2" placeholder="Ghi chú thêm..."></textarea>
            </div>
        </div>
        <div class="modal__footer">
            <button class="btn btn--outline" onclick="closeEditModal()">Hủy</button>
            <button class="btn btn--primary" onclick="saveConfig()">Lưu thay đổi</button>
        </div>
    </div>
</div>

<script>
    window.APP_CONFIG = { API_URL: '<?= API_URL ?>', CAMERA_ID: <?= $cameraId ?> };
</script>

<?php include __DIR__ . '/includes/footer.php'; ?>