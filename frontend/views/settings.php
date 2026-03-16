<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'CẤU HÌNH HỆ THỐNG',
    activePage: 'settings',
    extraJs: ['/assets/js/pages/SettingsController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-2">
    <h1 class="uppercase bold" style="font-size: 1.5rem;">Cấu hình mạng lưới & Nền tảng cốt lõi</h1>
    <p class="text-dim uppercase" style="font-size: 0.7rem;">Cảnh báo: Thay đổi tham số hệ thống có thể gây gián đoạn
        kết nối thiết bị đầu cuối.</p>
</div>

<form id="settings-form">
    <div class="settings-grid">
        <!-- IoT Broker Config -->
        <div class="g-card">
            <div class="g-card__header">
                <span class="g-card__title">ThingsBoard Broker</span>
                <span class="badge badge--online">MQTT</span>
            </div>
            <div class="g-card__body">
                <div class="form-group">
                    <label class="g-label">MQTT Endpoint Host</label>
                    <input type="text" name="mqtt_host" class="g-input font-mono text-primary"
                        placeholder="thingsboard.cloud" required>
                </div>
                <div class="form-group">
                    <label class="g-label">Cổng kết nối (Port)</label>
                    <input type="number" name="mqtt_port" class="g-input font-mono" placeholder="1883" required>
                </div>
            </div>
        </div>

        <!-- AI Core Config -->
        <div class="g-card">
            <div class="g-card__header">
                <span class="g-card__title">Lõi phân tích thị giác (AI Vision)</span>
                <span class="badge badge--online">TENSOR</span>
            </div>
            <div class="g-card__body">
                <div class="form-group">
                    <label class="g-label">Ngưỡng tin cậy tối thiểu (Confidence Threshold)</label>
                    <div class="flex-between" style="gap:12px;">
                        <input type="number" name="ai_confidence_threshold" step="0.01" min="0.1" max="1.0"
                            class="g-input font-mono text-primary" required>
                        <span class="text-dim">%</span>
                    </div>
                </div>
                <p class="text-dim mt-1" style="font-size:0.65rem;">Hệ thống sẽ loại bỏ các bản ghi có độ tin cậy dưới
                    ngưỡng thiết lập.</p>
            </div>
        </div>

        <!-- Data Retention Config -->
        <div class="g-card">
            <div class="g-card__header">
                <span class="g-card__title">Vòng đời dữ liệu</span>
                <span class="badge badge--offline">STORAGE</span>
            </div>
            <div class="g-card__body">
                <div class="form-group">
                    <label class="g-label">Lưu trữ vi phạm tối đa</label>
                    <div class="flex-between" style="gap:12px;">
                        <input type="number" name="retention_days" class="g-input font-mono" placeholder="30" required>
                        <span class="text-dim">NGÀY</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="submit-bar mt-2">
        <button type="button" class="btn btn--outline" onclick="location.reload()">HỦY BỎ THAY ĐỔI</button>
        <button type="submit" id="btn-save-settings" class="btn btn--primary">LƯU CẤU HÌNH</button>
    </div>
</form>

<style>
    .settings-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
        gap: 32px;
    }

    .form-group {
        margin-bottom: 24px;
    }

    .g-label {
        display: block;
        font-size: 0.65rem;
        font-weight: 800;
        text-transform: uppercase;
        color: var(--color-text-dim);
        margin-bottom: 8px;
    }

    .g-input {
        width: 100%;
        background: #000;
        border: 1px solid var(--color-border);
        padding: 12px 16px;
        color: #fff;
        font-family: var(--font-main);
        font-weight: 700;
        border-radius: var(--radius);
        transition: border-color 0.2s;
    }

    .g-input.font-mono {
        font-family: var(--font-mono);
    }

    .g-input:focus {
        border-color: var(--color-primary);
        outline: none;
    }

    .mt-1 {
        margin-top: 16px;
    }

    .mt-2 {
        margin-top: 32px;
    }

    .submit-bar {
        display: flex;
        justify-content: flex-end;
        gap: 16px;
        padding-top: 24px;
        border-top: 1px solid var(--color-border);
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>