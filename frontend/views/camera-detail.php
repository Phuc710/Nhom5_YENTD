<?php
use Frontend\App\Core\Page;

$cameraId = isset($id) ? (int) $id : (int) ($cameraId ?? 0);
$page = new Page(
    title: 'CHI TIẾT THIẾT BỊ',
    activePage: 'cameras',
    extraJs: ['/assets/js/pages/CameraController.js'],
    appConfig: ['CAMERA_ID' => $cameraId],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-2 flex-between">
    <div>
        <h1 class="bold uppercase" style="font-size: 2.2rem; line-height: 1;">
            Chi tiết <span class="text-primary">Thiết bị</span>
        </h1>
        <p class="text-dim uppercase bold mt-1" style="font-size: 0.65rem; letter-spacing: 0.15em;">
            Thông tin thiết bị #<span id="cam-id">0000</span> • Giám sát AI
        </p>
    </div>
    <div class="header-actions flex gap-1">
        <div id="cam-status-badge"></div>
        <button class="btn btn--outline btn--sm" onclick="controller.reboot()">KHỞI ĐỘNG LẠI</button>
    </div>
</div>

<div class="view-shell">
    <div class="main-column">
        <!-- Tab Navigation - Silicon Style -->
        <div class="tab-nav mb-2">
            <button class="tab-btn active" data-tab="live">
                <span class="tab-btn__text">GIÁM SÁT TRỰC TUYẾN</span>
            </button>
            <button class="tab-btn" data-tab="zones">
                <span class="tab-btn__text">CẤU HÌNH VÙNG</span>
            </button>
            <button class="tab-btn" data-tab="settings">
                <span class="tab-btn__text">THIẾT LẬP CHUYÊN SÂU</span>
            </button>
        </div>

        <!-- Tab: Live View -->
        <div class="tab-content active" id="tab-live">
            <div class="g-card stream-container glass-panel">
                <div class="mjpeg-wrapper">
                    <div class="stream-content">
                        <img id="camera-stream" src="" alt="Live Stream">
                        <div id="ai-boxes"></div>
                    </div>
                    <!-- Ambient Overlay -->
                    <div class="stream-ambient-top">
                        <div class="flex-between w-full">
                            <span class="badge badge--online">ĐANG GIÁM SÁT</span>
                            <div id="overlay-clock" class="font-mono text-xs opacity-50"></div>
                        </div>
                    </div>
                </div>

                <div class="stream-info-bar flex-between">
                    <div class="control-group">
                        <button class="btn btn--primary btn--sm" id="btn-stream-toggle">Dừng Live Stream</button>
                        <div class="v-divider"></div>
                        <div class="traffic-controls">
                            <button class="light-btn light-btn--red" onclick="controller.setLight('red')"></button>
                            <button class="light-btn light-btn--yellow"
                                onclick="controller.setLight('yellow')"></button>
                            <button class="light-btn light-btn--green" onclick="controller.setLight('green')"></button>
                        </div>
                    </div>
                    <div class="font-mono text-dim" style="font-size: 0.65rem;">
                        Kết nối bảo mật • Live Stream v2
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab: Config Zones -->
        <div class="tab-content" id="tab-zones">
            <div class="g-card glass-panel">
                <div class="g-card__header">
                    <span class="g-card__title">Thiết đặt Không gian</span>
                    <button class="btn btn--primary btn--sm" id="btn-save-zones">TRIỂN KHAI VÙNG</button>
                </div>
                <div class="canvas-wrapper">
                    <canvas id="zone-canvas"></canvas>
                    <div class="canvas-toolbar">
                        <button class="btn btn--sm btn--outline" data-tool="stop_line">VẠCH DỪNG</button>
                        <button class="btn btn--sm btn--outline" data-tool="violation_zone">VÙNG VI PHẠM</button>
                        <button class="btn btn--sm btn--outline" data-tool="detection_zone">VÙNG NHẬN DIỆN</button>
                        <div class="v-divider"></div>
                        <button class="btn btn--sm text-error" id="btn-clear-zones">XÓA TẤT CẢ</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tab: Settings -->
        <div class="tab-content" id="tab-settings">
            <div class="settings-grid-layout">
                <div class="g-card glass-panel">
                    <div class="g-card__header"><span class="g-card__title">Cấu hình nhận diện AI</span></div>
                    <div class="g-card__body">
                        <div class="form-group mb-2">
                            <div class="flex-between mb-1">
                                <label class="uppercase bold text-dim" style="font-size: 0.6rem;">Độ chính xác
                                    AI</label>
                                <span id="val-conf" class="font-mono text-primary">0.50</span>
                            </div>
                            <input type="range" min="0.1" max="1.0" step="0.05" id="input-conf" class="premium-slider">
                        </div>

                        <div class="form-group">
                            <label class="uppercase bold text-dim mb-1" style="font-size: 0.6rem;">Chế độ vận
                                hành</label>
                            <div class="select-wrapper">
                                <select class="premium-select" id="input-mode">
                                    <option value="balanced">Cân bằng</option>
                                    <option value="performance">Ưu tiên tốc độ</option>
                                    <option value="accuracy">Ưu tiên chính xác</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="g-card glass-panel">
                    <div class="g-card__header"><span class="g-card__title">Cấu hình hướng Camera</span></div>
                    <div class="g-card__body">
                        <div class="toggle-list">
                            <div class="toggle-item flex-between">
                                <div>
                                    <div class="bold" style="font-size: 0.8rem;">Xoay 180°</div>
                                    <div class="text-dim" style="font-size: 0.6rem;">Đảo ngược hình ảnh camera</div>
                                </div>
                                <label class="premium-switch">
                                    <input type="checkbox" id="check-rotate-180" checked>
                                    <span class="switch-slider"></span>
                                </label>
                            </div>
                            <div class="v-divider-h"></div>
                            <div class="toggle-item flex-between">
                                <div>
                                    <div class="bold" style="font-size: 0.8rem;">Lật Ngang</div>
                                    <div class="text-dim" style="font-size: 0.6rem;">Lật trục X để giám sát phía sau
                                    </div>
                                </div>
                                <label class="premium-switch">
                                    <input type="checkbox" id="check-flip-horizontal" checked>
                                    <span class="switch-slider"></span>
                                </label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="mt-2 text-right">
                <button class="btn btn--primary" style="width: 240px;" id="btn-save-settings">ĐỒNG BỘ THÔNG SỐ</button>
            </div>
        </div>
    </div>

    <aside class="info-sidebar">
        <div class="g-card glass-panel mb-2">
            <div class="g-card__header"><span class="g-card__title">Thông số cảm biến</span></div>
            <div class="g-card__body">
                <div class="telemetry-compact-grid">
                    <div class="tel-box">
                        <span class="tel-box__label">NHIỆT ĐỘ</span>
                        <span class="tel-box__value" id="tel-temp">--</span>
                    </div>
                    <div class="tel-box">
                        <span class="tel-box__label">TÍN HIỆU</span>
                        <span class="tel-box__value" id="tel-rssi">--</span>
                    </div>
                </div>

                <div class="system-pills mt-2">
                    <div class="sys-pill">
                        <span class="status-dot" id="pill-camera"></span>
                        <span class="sys-pill__text">Cảm biến: OK</span>
                    </div>
                    <div class="sys-pill">
                        <span class="status-dot" id="pill-mqtt"></span>
                        <span class="sys-pill__text">Kết nối: OK</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="g-card glass-panel">
            <div class="g-card__header"><span class="g-card__title">Thông tin thiết bị</span></div>
            <div class="g-card__body p-0">
                <div class="identity-list">
                    <div class="id-row">
                        <span class="id-row__label">Tên camera</span>
                        <span class="id-row__value" id="cam-name">--</span>
                    </div>
                    <div class="id-row">
                        <span class="id-row__label">Địa chỉ MAC</span>
                        <span class="id-row__value font-mono" id="cam-mac">--</span>
                    </div>
                    <div class="id-row">
                        <span class="id-row__label">Địa chỉ IP</span>
                        <span class="id-row__value font-mono" id="cam-ip">--</span>
                    </div>
                    <div class="id-row">
                        <span class="id-row__label">Vị trí lắp đặt</span>
                        <span class="id-row__value" id="cam-loc">--</span>
                    </div>
                </div>
                <div class="p-2 space-y-1">
                    <button class="btn btn--outline btn--block btn--sm" onclick="controller.startOTA()">CẬP NHẬT
                        OTA</button>
                    <button class="btn btn--outline btn--block btn--sm text-error"
                        onclick="controller.factoryReset()">KHÔI PHỤC CÀI ĐẶT GỐC</button>
                </div>
            </div>
        </div>
    </aside>
</div>

<style>
    .view-shell {
        display: grid;
        grid-template-columns: 1fr 320px;
        gap: 32px;
    }

    /* Premium Tab System */
    .tab-nav {
        display: flex;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid var(--color-border);
        border-radius: var(--radius-lg);
        padding: 6px;
        gap: 6px;
    }

    .tab-btn {
        flex: 1;
        background: transparent;
        border: none;
        color: var(--color-text-dim);
        font-family: var(--font-main);
        font-weight: 900;
        font-size: 0.75rem;
        padding: 12px;
        cursor: pointer;
        letter-spacing: 0.1em;
        transition: all 0.3s cubic-bezier(0.19, 1, 0.22, 1);
        border-radius: var(--radius);
        position: relative;
    }

    .tab-btn:hover {
        color: #fff;
        background: rgba(255, 255, 255, 0.05);
    }

    .tab-btn.active {
        background: var(--color-primary);
        color: #000;
        box-shadow: 0 4px 15px var(--color-primary-glow);
    }

    .tab-content {
        display: none;
    }

    .tab-content.active {
        display: block;
        animation: fadeIn 0.4s ease;
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(10px);
        }

        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    /* Stream UI v2 */
    .stream-container {
        position: relative;
    }

    .mjpeg-wrapper {
        background: #000;
        aspect-ratio: 16/9;
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        border-bottom: 1px solid var(--color-border);
    }

    .stream-ambient-top {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        padding: 16px 20px;
        background: linear-gradient(to bottom, rgba(0, 0, 0, 0.8) 0%, transparent 100%);
        z-index: 5;
    }

    .stream-info-bar {
        padding: 20px 24px;
        background: rgba(0, 0, 0, 0.2);
    }

    .traffic-controls {
        display: flex;
        gap: 10px;
        padding: 4px;
        background: #000;
        border-radius: 20px;
        border: 1px solid var(--color-border);
    }

    .light-btn {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        border: none;
        cursor: pointer;
        transition: transform 0.2s;
        opacity: 0.4;
        filter: blur(1px);
    }

    .light-btn:hover {
        transform: scale(1.2);
        opacity: 1;
        filter: none;
    }

    .light-btn--red {
        background: #ff4444;
        box-shadow: 0 0 10px #ff4444;
    }

    .light-btn--yellow {
        background: #ffbb33;
        box-shadow: 0 0 10px #ffbb33;
    }

    .light-btn--green {
        background: #00C851;
        box-shadow: 0 0 10px #00C851;
    }

    /* AI Bounding Boxes (Custom V3) */
    .ai-bbox {
        position: absolute;
        border: 2px solid;
        box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
        z-index: 10;
    }

    .ai-bbox-label {
        position: absolute;
        top: -20px;
        left: -2px;
        color: #000;
        background: var(--color-primary);
        font-family: var(--font-mono);
        font-size: 0.6rem;
        font-weight: 800;
        padding: 2px 6px;
        border-radius: 2px;
    }

    /* Premium Switches */
    .premium-switch {
        position: relative;
        display: inline-block;
        width: 44px;
        height: 24px;
    }

    .premium-switch input {
        opacity: 0;
        width: 0;
        height: 0;
    }

    .switch-slider {
        position: absolute;
        cursor: pointer;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: var(--color-surface-soft);
        transition: .4s;
        border-radius: 34px;
        border: 1px solid var(--color-border);
    }

    .switch-slider:before {
        position: absolute;
        content: "";
        height: 16px;
        width: 16px;
        left: 3px;
        bottom: 3px;
        background-color: var(--color-text-dim);
        transition: .4s;
        border-radius: 50%;
    }

    input:checked+.switch-slider {
        background-color: var(--color-primary);
        border-color: var(--color-primary);
    }

    input:checked+.switch-slider:before {
        transform: translateX(20px);
        background-color: #000;
    }

    /* Sliders & Selects */
    .premium-slider {
        -webkit-appearance: none;
        width: 100%;
        height: 6px;
        background: var(--color-surface-soft);
        border-radius: 5px;
        outline: none;
        border: 1px solid var(--color-border);
    }

    .premium-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 18px;
        height: 18px;
        background: var(--color-primary);
        cursor: pointer;
        border-radius: 50%;
        box-shadow: 0 0 10px var(--color-primary-glow);
    }

    .premium-select {
        width: 100%;
        background: var(--color-surface-soft);
        border: 1px solid var(--color-border);
        color: #fff;
        padding: 12px 16px;
        border-radius: var(--radius);
        font-family: var(--font-mono);
        font-size: 0.75rem;
        cursor: pointer;
        outline: none;
    }

    /* Telemetry Sidebar */
    .telemetry-compact-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
    }

    .tel-box {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid var(--color-border);
        padding: 16px;
        border-radius: var(--radius);
        text-align: center;
    }

    .tel-box__label {
        font-size: 0.6rem;
        font-weight: 900;
        color: var(--color-text-dim);
        display: block;
        margin-bottom: 4px;
    }

    .tel-box__value {
        font-size: 1.2rem;
        font-weight: 900;
        color: #fff;
        font-family: var(--font-mono);
    }

    .sys-pill {
        display: flex;
        align-items: center;
        margin-bottom: 12px;
        border: 1px solid var(--color-border);
        padding: 8px 12px;
        border-radius: var(--radius-sm);
        background: rgba(0, 0, 0, 0.2);
    }

    .sys-pill__text {
        font-size: 0.65rem;
        font-weight: 900;
        color: var(--color-text-muted);
        letter-spacing: 0.05em;
    }

    .identity-list {
        border-top: 1px solid var(--color-border);
    }

    .id-row {
        padding: 12px 20px;
        border-bottom: 1px solid var(--color-border);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    .id-row__label {
        font-size: 0.6rem;
        font-weight: 800;
        color: var(--color-text-dim);
        text-transform: uppercase;
    }

    .id-row__value {
        font-size: 0.75rem;
        font-weight: 700;
        color: #fff;
    }

    .v-divider {
        width: 1px;
        height: 24px;
        background: var(--color-border);
    }

    .v-divider-h {
        width: 100%;
        height: 1px;
        background: var(--color-border);
        margin: 12px 0;
    }

    .p-2 {
        padding: 20px;
    }

    .p-0 {
        padding: 0 !important;
    }

    .space-y-1>*+* {
        margin-top: 10px;
    }

    .gap-1 {
        gap: 12px;
    }

    .btn--block {
        width: 100%;
    }

    /* Canvas Drawing */
    .canvas-wrapper {
        position: relative;
        background: #000;
        aspect-ratio: 16/9;
    }

    #zone-canvas {
        width: 100%;
        height: 100%;
        cursor: crosshair;
    }

    .canvas-toolbar {
        position: absolute;
        bottom: 24px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        gap: 12px;
        background: rgba(0, 0, 0, 0.8);
        padding: 8px 16px;
        border-radius: 40px;
        border: 1px solid var(--color-border);
        backdrop-filter: blur(10px);
        z-index: 10;
    }

    .settings-grid-layout {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 24px;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>