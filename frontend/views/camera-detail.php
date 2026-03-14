<?php
use Frontend\App\Core\Page;

$cameraId = $id ?? 0;

$page = new Page(
    title: "Quan ly Camera #$cameraId",
    activePage: 'cameras',
    extraCss: ['/assets/css/pages/camera-detail.css'],
    extraJs: ['/assets/js/zone-editor.js', '/assets/js/camera.js'],
    appConfig: ['CAMERA_ID' => $cameraId]
);

include __DIR__ . '/../includes/header.php';
?>

<div class="detail-layout">
    <div class="detail-main">
        <div class="card mb-2">
            <div class="card__header">
                <span class="card__title">Luong truc tiep</span>
                <div id="streamInfo" class="text-dim" style="font-size:0.8rem;">Dang ket noi...</div>
            </div>
            <div class="card__body" style="padding:0;">
                <div class="stream-container">
                    <img id="streamImg" src="" alt="Stream Feed">
                    <div id="streamBboxLayer" class="stream-bbox-layer"></div>
                    <div class="stream-overlay-info">
                        <span id="overlayClock">00:00:00</span>
                        <span id="overlayFps">-- ms</span>
                    </div>
                </div>
            </div>
        </div>

        <nav class="tab-nav mb-2">
            <button class="tab-btn active" data-tab="violations">Vi pham gan day</button>
            <button class="tab-btn" data-tab="detect">Detect anh</button>
            <button class="tab-btn" data-tab="zones">Zones</button>
            <button class="tab-btn" data-tab="control">Dieu khien den</button>
            <button class="tab-btn" data-tab="settings">Cau hinh thiet bi</button>
        </nav>

        <div id="tabViolations" class="tab-content">
            <div class="card">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Anh</th>
                                <th>Bien so</th>
                                <th>Thoi gian</th>
                                <th>Tin cay</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody id="recentList">
                            <tr>
                                <td colspan="5" style="text-align:center; padding:40px;" class="text-muted">Dang tai du lieu...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div id="tabDetect" class="tab-content hidden">
            <div class="card">
                <div class="card__header">
                    <span class="card__title">Up anh detect hang loat</span>
                    <div class="text-dim" style="font-size:0.8rem;">Bao nhieu BSX detect duoc thi tra ra bay nhieu dong</div>
                </div>
                <div class="card__body">
                    <div class="settings-form">
                        <div class="form-group mb-2">
                            <label class="form-label">Anh JPEG/PNG</label>
                            <input type="file" id="detectUploadInput" class="form-input" accept="image/*">
                        </div>
                        <div style="display:flex; gap:12px; margin-top:16px; align-items:center; flex-wrap:wrap;">
                            <button class="btn btn--primary" id="btnDetectUpload">Detect va luu</button>
                            <span id="detectUploadStatus" class="text-dim">Chua chon anh</span>
                        </div>
                        <div id="detectUploadSummary" class="text-dim" style="margin-top:18px;"></div>
                        <div id="detectUploadResults" class="detect-results-grid" style="margin-top:18px;"></div>
                    </div>
                </div>
            </div>
        </div>

        <div id="tabZones" class="tab-content hidden">
            <div class="card">
                <div class="card__header">
                    <span class="card__title">Zone editor</span>
                    <div class="text-dim" style="font-size:0.8rem;">Ve vung detection/roi, backend se chi detect trong cac vung nay</div>
                </div>
                <div class="card__body">
                    <div style="display:flex; gap:12px; flex-wrap:wrap; align-items:center; margin-bottom:16px;">
                        <select id="zoneTypeSelect" class="form-input" style="width:auto; min-width:180px;">
                            <option value="detection">Detection Zone</option>
                            <option value="roi">ROI Zone</option>
                            <option value="stop_line">Stop Line</option>
                        </select>
                        <button class="btn btn--outline" id="btnReloadZones">Tai lai zones</button>
                        <button class="btn btn--outline" id="btnClearZones">Xoa het tam</button>
                        <button class="btn btn--primary" id="btnSaveZones">Luu zones</button>
                        <span id="zoneStatus" class="text-dim">Chua tai zones</span>
                    </div>
                    <div class="zone-editor-wrap">
                        <img id="zoneEditorImg" src="" alt="Zone Snapshot">
                    </div>
                    <div class="text-dim" style="margin-top:12px;">Keo tha de ve box. Nhan label de doi ten zone.</div>
                </div>
            </div>
        </div>

        <div id="tabControl" class="tab-content hidden">
            <div class="card">
                <div class="card__body tl-panel">
                    <div class="tl-status">
                        <div class="tl-light tl-light--red" id="dotRed"></div>
                        <div class="tl-light tl-light--yellow" id="dotYellow"></div>
                        <div class="tl-light tl-light--green" id="dotGreen"></div>
                    </div>
                    <div class="tl-controls">
                        <h3 style="margin-bottom:16px; font-size:1rem;">Ghi den thu cong</h3>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                            <button class="btn btn--outline" onclick="setLight('RED')">Do</button>
                            <button class="btn btn--outline" onclick="setLight('GREEN')">Xanh</button>
                            <button class="btn btn--outline" onclick="setLight('YELLOW')">Vang</button>
                            <button class="btn btn--outline" onclick="setLight('AUTO')">Tu dong</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div id="tabSettings" class="tab-content hidden">
            <div class="card">
                <div class="card__body">
                    <div class="settings-form">
                        <div class="form-group mb-2">
                            <label class="form-label">Ten Camera</label>
                            <input type="text" id="cfgName" class="form-input" placeholder="Nhap ten...">
                        </div>
                        <div class="form-group mb-2">
                            <label class="form-label">Vi tri lap dat</label>
                            <input type="text" id="cfgLocation" class="form-input" placeholder="Vi du: Nga tu A...">
                        </div>
                        <div style="display:flex; gap:12px; margin-top:24px; flex-wrap:wrap;">
                            <button class="btn btn--primary" onclick="saveSettings()">Luu cau hinh</button>
                            <button class="btn btn--outline" onclick="factoryReset()">Khoi phuc cai dat goc</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <aside class="detail-sidebar">
        <div class="card">
            <div class="card__header">
                <span class="card__title">Thong tin thiet bi</span>
            </div>
            <div class="card__body">
                <div class="info-list">
                    <div class="info-row">
                        <span class="info-label">Trang thai</span>
                        <span class="info-value" id="camStatus">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Dia chi IP</span>
                        <span class="info-value" id="camIp">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Dia chi MAC</span>
                        <span class="info-value" id="camMac">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Phien ban FW</span>
                        <span class="info-value" id="camFw">--</span>
                    </div>
                </div>
                <button class="btn btn--outline" style="width:100%; margin-top:20px;" id="btnReboot">Khoi dong lai</button>
            </div>
        </div>
    </aside>
</div>

<style>
    .detail-layout { display:grid; grid-template-columns:1fr 300px; gap:24px; align-items:start; }
    .stream-container { width:100%; aspect-ratio:16/9; background:#000; position:relative; }
    .stream-container img { width:100%; height:100%; object-fit:contain; }
    .stream-bbox-layer { position:absolute; inset:0; pointer-events:none; }
    .stream-bbox {
        position:absolute;
        border:2px solid #00e0ff;
        box-shadow:0 0 0 1px rgba(0,0,0,.24) inset, 0 0 20px rgba(0,224,255,.2);
        border-radius:8px;
    }
    .stream-bbox--warning {
        border-color:#f59e0b;
        box-shadow:0 0 0 1px rgba(0,0,0,.24) inset, 0 0 20px rgba(245,158,11,.22);
    }
    .stream-bbox--violation {
        border-color:#ef4444;
        box-shadow:0 0 0 1px rgba(0,0,0,.24) inset, 0 0 20px rgba(239,68,68,.28);
    }
    .stream-bbox__label {
        position:absolute;
        top:-30px;
        left:0;
        background:rgba(0,224,255,.95);
        color:#031118;
        padding:4px 8px;
        border-radius:999px;
        font-size:.72rem;
        font-weight:800;
        white-space:nowrap;
    }
    .stream-overlay-info {
        position:absolute; bottom:16px; right:16px; display:flex; gap:12px;
        background:rgba(0,0,0,.6); padding:4px 12px; border-radius:4px;
        font-family:monospace; font-size:.8rem;
    }
    .tab-nav { display:flex; gap:4px; border-bottom:2px solid #1f1f1f; flex-wrap:wrap; }
    .tab-btn {
        background:transparent; border:none; color:var(--color-text-dim); padding:12px 20px;
        font-weight:700; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-2px; transition:all .2s;
    }
    .tab-btn:hover { color:var(--color-text-main); }
    .tab-btn.active { color:var(--color-primary); border-bottom-color:var(--color-primary); }
    .hidden { display:none; }
    .tl-panel { display:grid; grid-template-columns:100px 1fr; gap:32px; align-items:center; }
    .tl-status { background:#050505; padding:16px; border-radius:12px; display:flex; flex-direction:column; gap:12px; align-items:center; }
    .tl-light { width:24px; height:24px; border-radius:50%; background:#111; border:1px solid #222; }
    .tl-light--red.active { background:var(--color-error); box-shadow:0 0 15px var(--color-error); }
    .tl-light--yellow.active { background:var(--color-warning); box-shadow:0 0 15px var(--color-warning); }
    .tl-light--green.active { background:var(--color-success); box-shadow:0 0 15px var(--color-success); }
    .info-list { display:flex; flex-direction:column; gap:12px; }
    .info-row { display:flex; justify-content:space-between; font-size:.85rem; }
    .info-label { color:var(--color-text-dim); }
    .info-value { font-weight:600; }
    .form-label { display:block; font-size:.75rem; font-weight:700; color:var(--color-text-dim); margin-bottom:8px; text-transform:uppercase; }
    .form-input { width:100%; background:#0a0a0a; border:1px solid #1f1f1f; padding:10px 14px; color:#fff; border-radius:4px; }
    .form-input:focus { border-color:var(--color-primary); outline:none; }
    .detect-results-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(260px, 1fr)); gap:16px; }
    .detect-card { border:1px solid #1f1f1f; border-radius:12px; overflow:hidden; background:#080808; }
    .detect-card__images { display:grid; grid-template-columns:1fr 1fr; gap:2px; background:#111; }
    .detect-card__images img { width:100%; aspect-ratio:4/3; object-fit:cover; background:#000; }
    .detect-card__body { padding:12px; display:grid; gap:8px; }
    .detect-card__plate { font-family:monospace; font-size:1rem; font-weight:800; color:#fff; }
    .zone-editor-wrap { position:relative; width:100%; aspect-ratio:16/9; background:#000; overflow:hidden; border-radius:12px; }
    .zone-editor-wrap img { width:100%; height:100%; object-fit:contain; display:block; }
    .zone-box {
        position:absolute; border:2px solid #22c55e; background:rgba(34,197,94,.12);
        border-radius:8px; pointer-events:auto;
    }
    .zone-box--stop-line { border-color:#f59e0b; background:rgba(245,158,11,.12); }
    .zone-box--selected { box-shadow:0 0 0 2px rgba(255,255,255,.18), 0 0 18px rgba(34,197,94,.25); }
    .zone-box__label {
        position:absolute; top:-28px; left:0; background:#22c55e; color:#041107;
        border-radius:999px; padding:4px 8px; font-size:.72rem; font-weight:800; min-width:64px;
    }
    .zone-box--stop-line .zone-box__label { background:#f59e0b; color:#160d02; }
    .zone-box__delete {
        position:absolute; top:6px; right:6px; width:22px; height:22px; border:none;
        border-radius:999px; background:rgba(0,0,0,.7); color:#fff; cursor:pointer;
    }
    .zone-box__handle {
        position:absolute; width:12px; height:12px; border-radius:999px; background:#fff; border:2px solid #111;
    }
    .zone-box__handle--tl { top:-6px; left:-6px; }
    .zone-box__handle--tr { top:-6px; right:-6px; }
    .zone-box__handle--bl { bottom:-6px; left:-6px; }
    .zone-box__handle--br { bottom:-6px; right:-6px; }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>
