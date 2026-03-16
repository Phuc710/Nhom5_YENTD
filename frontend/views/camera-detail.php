<?php
use Frontend\App\Core\Page;

$cameraId = isset($id) ? (int) $id : (int) ($cameraId ?? 0);
$page = new Page(
    title: 'CHI TIET THIET BI',
    activePage: 'cameras',
    extraJs: ['/assets/js/pages/CameraController.js'],
    appConfig: ['CAMERA_ID' => $cameraId],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-shell">
    <div class="stream-panel">
        <div class="g-card stream-container">
            <div class="stream-header">
                <div class="flex-between">
                    <div>
                        <span class="badge badge--online" style="margin-right: 10px;">LIVE FEED</span>
                        <span class="font-mono text-dim">REC // <span id="cam-id">0000</span></span>
                    </div>
                    <div id="cam-status-badge"></div>
                </div>
            </div>

            <div class="mjpeg-wrapper">
                <div class="stream-content">
                    <img id="camera-stream" src="" alt="Live Stream">
                    <div id="ai-boxes"></div>
                </div>
                <div class="stream-overlay">
                    <div id="overlay-clock" class="font-mono"></div>
                </div>
            </div>

            <div class="stream-controls flex-between">
                <div class="control-group">
                    <button class="btn btn--outline btn--sm" onclick="controller.setLight('red')">RED</button>
                    <button class="btn btn--outline btn--sm" onclick="controller.setLight('yellow')">YELLOW</button>
                    <button class="btn btn--outline btn--sm" onclick="controller.setLight('green')">GREEN</button>
                </div>
                <div class="control-group">
                    <button class="btn btn--primary btn--sm" onclick="controller.reboot()">REBOOT</button>
                    <button class="btn btn--outline btn--sm" onclick="controller.startOTA()">OTA</button>
                </div>
            </div>
        </div>
    </div>

    <aside class="info-sidebar">
        <div class="g-card mb-1">
            <div class="g-card__header"><span class="g-card__title">THONG SO PHAN CUNG</span></div>
            <div class="g-card__body">
                <div class="tel-grid">
                    <div class="tel-item">
                        <div class="tel-label">WiFi RSSI</div>
                        <div class="tel-value font-mono" id="tel-rssi">--</div>
                    </div>
                    <div class="tel-item">
                        <div class="tel-label">Nhiet do CPU</div>
                        <div class="tel-value font-mono" id="tel-temp">--</div>
                    </div>
                    <div class="tel-item">
                        <div class="tel-label">Free Heap</div>
                        <div class="tel-value font-mono" id="tel-heap">--</div>
                    </div>
                </div>

                <div class="status-indicators mb-1">
                    <div class="status-indicator">
                        <span class="status-pill" id="pill-camera"></span>
                        <span class="text-dim">Cam bien Camera</span>
                    </div>
                    <div class="status-indicator">
                        <span class="status-pill" id="pill-mqtt"></span>
                        <span class="text-dim">Ket noi ThingsBoard</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="g-card">
            <div class="g-card__header"><span class="g-card__title">DINH DANH THIET BI</span></div>
            <div class="g-card__body">
                <div class="prop-list">
                    <div class="prop-item">
                        <span class="prop-label">Ten thiet bi</span>
                        <span class="prop-value" id="cam-name">--</span>
                    </div>
                    <div class="prop-item">
                        <span class="prop-label">Dia chi MAC</span>
                        <span class="prop-value font-mono" id="cam-mac">--</span>
                    </div>
                    <div class="prop-item">
                        <span class="prop-label">Dia chi IP</span>
                        <span class="prop-value font-mono" id="cam-ip">--</span>
                    </div>
                    <div class="prop-item">
                        <span class="prop-label">Vi tri</span>
                        <span class="prop-value" id="cam-loc">--</span>
                    </div>
                    <div class="prop-item">
                        <span class="prop-label">Firmware</span>
                        <span class="prop-value" id="cam-fw">--</span>
                    </div>
                    <div class="prop-item">
                        <span class="prop-label">IDF Version</span>
                        <span class="prop-value" id="cam-idf">--</span>
                    </div>
                </div>
                <button class="btn btn--outline btn--sm"
                    style="width: 100%; margin-top: 16px; color: var(--color-error);"
                    onclick="controller.factoryReset()">FACTORY RESET</button>
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

    .mjpeg-wrapper {
        background: #000;
        aspect-ratio: 16/9;
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        border-top: 1px solid var(--color-border);
        border-bottom: 1px solid var(--color-border);
        overflow: hidden;
    }

    .stream-content {
        position: relative;
        display: inline-block;
        max-width: 100%;
        max-height: 100%;
    }

    .stream-content img {
        display: block;
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
    }

    #ai-boxes {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
    }

    .stream-header {
        padding: 12px 20px;
    }

    .ai-bbox {
        position: absolute;
        border: 2px solid;
        box-sizing: border-box;
        pointer-events: none;
        z-index: 10;
        transition: all 0.1s linear;
    }

    .ai-bbox-label {
        position: absolute;
        top: -16px;
        left: -2px;
        color: #fff;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.6rem;
        font-weight: 700;
        padding: 2px 4px;
        white-space: nowrap;
        pointer-events: none;
    }

    .stream-overlay {
        position: absolute;
        top: 10px;
        right: 10px;
        z-index: 20;
    }

    #overlay-clock {
        background: rgba(0, 0, 0, 0.7);
        padding: 4px 8px;
        color: var(--color-primary);
        font-size: 0.75rem;
        font-weight: bold;
        border: 1px solid var(--color-border);
    }

    .stream-controls {
        padding: 16px 20px;
    }

    .control-group {
        display: flex;
        gap: 8px;
    }

    .tel-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
        margin-bottom: 20px;
    }

    .tel-item {
        padding: 12px;
        background: var(--color-surface-soft);
        border: 1px solid var(--color-border);
    }

    .tel-label {
        font-size: 0.65rem;
        font-weight: 800;
        text-transform: uppercase;
        color: var(--color-text-dim);
        margin-bottom: 4px;
    }

    .tel-value {
        font-size: 1.1rem;
        font-weight: 700;
        color: var(--color-primary);
    }

    .prop-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .prop-item {
        display: flex;
        flex-direction: column;
        gap: 2px;
    }

    .prop-label {
        font-size: 0.65rem;
        font-weight: 800;
        text-transform: uppercase;
        color: var(--color-text-dim);
    }

    .prop-value {
        font-size: 0.85rem;
        font-weight: 700;
    }

    .status-pill {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
    }

    .status-pill--online {
        background: var(--color-success);
        box-shadow: 0 0 8px var(--color-success);
    }

    .status-pill--offline {
        background: var(--color-error);
        box-shadow: 0 0 8px var(--color-error);
    }

    .status-indicator {
        display: flex;
        align-items: center;
        margin-bottom: 8px;
        font-size: 0.75rem;
        font-weight: 700;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>
