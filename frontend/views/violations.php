<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'NHẬT KÝ VI PHẠM',
    activePage: 'violations',
    extraJs: ['/assets/js/pages/ViolationController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-2">
    <div class="flex-between">
        <h1 class="uppercase bold" style="font-size: 1.5rem;">Hệ thống lưu trữ vi phạm</h1>
        <div class="flex-between" style="gap: 12px;">
            <button class="btn btn--outline btn--sm range-btn btn--primary"
                onclick="controller.setRange('all', this)">TẤT CẢ</button>
            <button class="btn btn--outline btn--sm range-btn" onclick="controller.setRange('today', this)">HÔM
                NAY</button>
            <button class="btn btn--outline btn--sm range-btn" onclick="controller.setRange('7d', this)">7 NGÀY</button>
        </div>
    </div>
</div>

<!-- Search & Filter Bar -->
<div class="g-card mb-2" style="background: var(--color-surface-soft); border-color: var(--color-border-bright);">
    <div class="g-card__body">
        <div class="filter-grid">
            <div class="filter-item">
                <label class="uppercase bold text-dim"
                    style="font-size: 0.6rem; display: block; margin-bottom: 8px;">Tìm biển số</label>
                <input type="text" id="filter-plate" class="g-input" placeholder="BIỂN SỐ..." autocomplete="off">
            </div>
            <div class="filter-item">
                <label class="uppercase bold text-dim"
                    style="font-size: 0.6rem; display: block; margin-bottom: 8px;">Lọc theo camera</label>
                <select id="filter-camera" class="g-input">
                    <option value="">TẤT CẢ CAMERA</option>
                </select>
            </div>
        </div>
    </div>
</div>

<div class="g-card">
    <div class="table-container">
        <table class="data-table">
            <thead>
                <tr>
                    <th style="width: 80px;">Hiện trường</th>
                    <th>Biển số xe</th>
                    <th>Nguồn thiết bị</th>
                    <th>Thời gian ghi nhận</th>
                    <th>Độ tin cậy AI</th>
                    <th style="text-align: right;">Thao tác</th>
                </tr>
            </thead>
            <tbody id="violation-table-body">
                <!-- Loaded via ViolationController -->
            </tbody>
        </table>
    </div>
</div>

<style>
    .filter-grid {
        display: grid;
        grid-template-columns: 2fr 1fr;
        gap: 24px;
    }

    .g-input {
        width: 100%;
        background: #000;
        border: 1px solid var(--color-border);
        padding: 12px 16px;
        color: #fff;
        font-family: var(--font-mono);
        font-weight: 700;
        text-transform: uppercase;
        border-radius: var(--radius);
    }

    .g-input:focus {
        border-color: var(--color-primary);
        outline: none;
    }

    .table-container {
        overflow-x: auto;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>