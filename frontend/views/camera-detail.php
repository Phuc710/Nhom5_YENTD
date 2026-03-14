<?php
use Frontend\App\Core\Page;

$cameraId = $id ?? 0;

$page = new Page(
    title: "Quản lý Camera #$cameraId",
    activePage: 'cameras',
    extraCss: ['/assets/css/pages/camera-detail.css'],
    extraJs: ['/assets/js/camera.js'],
    appConfig: ['CAMERA_ID' => $cameraId]
);

include __DIR__ . '/../includes/header.php';
?>

<div class="detail-layout">
    <!-- Main Content Area -->
    <div class="detail-main">
        <div class="card mb-2">
            <div class="card__header">
                <span class="card__title">Luồng trực tiếp</span>
                <div id="streamInfo" class="text-dim" style="font-size: 0.8rem;">Đang kết nối...</div>
            </div>
            <div class="card__body" style="padding: 0;">
                <div class="stream-container">
                    <img id="streamImg" src="" alt="Stream Feed">
                    <div class="stream-overlay-info">
                        <span id="overlayClock">00:00:00</span>
                        <span id="overlayFps">-- FPS</span>
                    </div>
                </div>
            </div>
        </div>

        <nav class="tab-nav mb-2">
            <button class="tab-btn active" data-tab="violations">Vi phạm gần đây</button>
            <button class="tab-btn" data-tab="control">Điều khiển đèn</button>
            <button class="tab-btn" data-tab="settings">Cấu hình thiết bị</button>
        </nav>

        <div id="tabViolations" class="tab-content">
            <div class="card">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Ảnh</th>
                                <th>Biển số</th>
                                <th>Thời gian</th>
                                <th>Tin cậy</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody id="recentList">
                            <tr>
                                <td colspan="5" style="text-align:center; padding:40px;" class="text-muted">Đang tải dữ
                                    liệu...</td>
                            </tr>
                        </tbody>
                    </table>
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
                        <h3 style="margin-bottom:16px; font-size:1rem;">Ghi đè thủ công</h3>
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                            <button class="btn btn--outline" onclick="setLight('RED')">Đỏ</button>
                            <button class="btn btn--outline" onclick="setLight('GREEN')">Xanh</button>
                            <button class="btn btn--outline" onclick="setLight('YELLOW')">Vàng</button>
                            <button class="btn btn--outline" onclick="setLight('AUTO')">Tự động</button>
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
                            <label class="form-label">Tên Camera</label>
                            <input type="text" id="cfgName" class="form-input" placeholder="Nhập tên...">
                        </div>
                        <div class="form-group mb-2">
                            <label class="form-label">Vị trí lắp đặt</label>
                            <input type="text" id="cfgLocation" class="form-input" placeholder="Ví dụ: Ngã tư A...">
                        </div>
                        <div style="display:flex; gap:12px; margin-top:24px;">
                            <button class="btn btn--primary" onclick="saveSettings()">Lưu cấu hình</button>
                            <button class="btn btn--outline" onclick="factoryReset()">Khôi phục cài đặt gốc</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Sidebar Info Panel -->
    <aside class="detail-sidebar">
        <div class="card">
            <div class="card__header">
                <span class="card__title">Thông tin thiết bị</span>
            </div>
            <div class="card__body">
                <div class="info-list">
                    <div class="info-row">
                        <span class="info-label">Trạng thái</span>
                        <span class="info-value" id="camStatus">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Địa chỉ IP</span>
                        <span class="info-value" id="camIp">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Địa chỉ MAC</span>
                        <span class="info-value" id="camMac">--</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Phiên bản FW</span>
                        <span class="info-value" id="camFw">--</span>
                    </div>
                </div>
                <button class="btn btn--outline" style="width:100%; margin-top:20px;" id="btnReboot">Khởi động
                    lại</button>
            </div>
        </div>
    </aside>
</div>

<style>
    .detail-layout {
        display: grid;
        grid-template-columns: 1fr 300px;
        gap: 24px;
        align-items: start;
    }

    .stream-container {
        width: 100%;
        aspect-ratio: 16/9;
        background: #000;
        position: relative;
    }

    .stream-container img {
        width: 100%;
        height: 100%;
        object-fit: contain;
    }

    .stream-overlay-info {
        position: absolute;
        bottom: 16px;
        right: 16px;
        display: flex;
        gap: 12px;
        background: rgba(0, 0, 0, 0.6);
        padding: 4px 12px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.8rem;
    }

    .tab-nav {
        display: flex;
        gap: 4px;
        border-bottom: 2px solid #1f1f1f;
    }

    .tab-btn {
        background: transparent;
        border: none;
        color: var(--color-text-dim);
        padding: 12px 20px;
        font-weight: 700;
        cursor: pointer;
        border-bottom: 2px solid transparent;
        margin-bottom: -2px;
        transition: all 0.2s;
    }

    .tab-btn:hover {
        color: var(--color-text-main);
    }

    .tab-btn.active {
        color: var(--color-primary);
        border-bottom-color: var(--color-primary);
    }

    .hidden {
        display: none;
    }

    .tl-panel {
        display: grid;
        grid-template-columns: 100px 1fr;
        gap: 32px;
        align-items: center;
    }

    .tl-status {
        background: #050505;
        padding: 16px;
        border-radius: 12px;
        display: flex;
        flex-direction: column;
        gap: 12px;
        align-items: center;
    }

    .tl-light {
        width: 24px;
        height: 24px;
        border-radius: 50%;
        background: #111;
        border: 1px solid #222;
    }

    .tl-light--red.active {
        background: var(--color-error);
        box-shadow: 0 0 15px var(--color-error);
    }

    .tl-light--yellow.active {
        background: var(--color-warning);
        box-shadow: 0 0 15px var(--color-warning);
    }

    .tl-light--green.active {
        background: var(--color-success);
        box-shadow: 0 0 15px var(--color-success);
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
        font-weight: 600;
    }

    .form-label {
        display: block;
        font-size: 0.75rem;
        font-weight: 700;
        color: var(--color-text-dim);
        margin-bottom: 8px;
        text-transform: uppercase;
    }

    .form-input {
        width: 100%;
        background: #0a0a0a;
        border: 1px solid #1f1f1f;
        padding: 10px 14px;
        color: #fff;
        border-radius: 4px;
    }

    .form-input:focus {
        border-color: var(--color-primary);
        outline: none;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>