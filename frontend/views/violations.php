<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'NHẬT KÝ VI PHẠM',
    activePage: 'violations',
    extraJs: ['/assets/js/pages/ViolationController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-3">
    <div class="flex-between">
        <div>
            <h1 class="bold uppercase" style="font-size: 2.5rem; line-height: 1.1; letter-spacing: -0.02em;">
                Nhật Ký <span class="text-primary">Vi Phạm</span>
            </h1>
            <p class="text-dim uppercase bold mt-1" style="font-size: 0.65rem; letter-spacing: 0.15em;">
                Dữ liệu giám sát & Tra cứu vi phạm
            </p>
        </div>
        <div class="flex-between g-card--glass" style="gap: 8px; padding: 6px; border-radius: 12px;">
            <button class="btn btn--sm range-btn btn--primary" onclick="controller.setRange('all', this)">TẤT
                CẢ</button>
            <button class="btn btn--sm range-btn text-dim" onclick="controller.setRange('today', this)">HÔM NAY</button>
            <button class="btn btn--sm range-btn text-dim" onclick="controller.setRange('7d', this)">7 NGÀY</button>
        </div>
    </div>
</div>

<!-- Search & Filter Bar -->
<div class="g-card g-card--glass mb-3">
    <div class="g-card__body p-3">
        <div class="filter-grid">
            <div class="filter-item">
                <label class="input-label">Biển số xe</label>
                <div style="position: relative;">
                    <i class="search-icon"
                        style="position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: var(--color-primary); opacity: 0.5;"></i>
                    <input type="text" id="filter-plate" class="g-input" placeholder="Nhập biển số xe..."
                        style="padding-left: 45px;">
                </div>
            </div>
            <div class="filter-item">
                <label class="input-label">Camera giám sát</label>
                <select id="filter-camera" class="g-input">
                    <option value="">Tất cả camera</option>
                </select>
            </div>
        </div>
    </div>
</div>

<div class="g-card g-card--glass">
    <div class="g-card__header border-bottom flex-between">
        <span class="g-card__title">Danh sách vi phạm</span>
        <span class="text-dim font-mono" style="font-size: 0.6rem;" id="record-count">-- BẢN GHI</span>
    </div>
    <div class="table-container">
        <table class="data-table">
            <thead>
                <tr>
                    <th style="width: 120px;">Hình ảnh</th>
                    <th>Biển số xe</th>
                    <th>Camera</th>
                    <th>Thời gian ghi nhận</th>
                    <th>Độ tin cậy AI</th>
                    <th style="text-align: right;">Hành động</th>
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
        grid-template-columns: 1.5fr 1fr;
        gap: 20px;
    }

    .table-container {
        overflow-x: auto;
    }

    .data-table th {
        background: rgba(0, 0, 0, 0.2);
        color: var(--color-text-dim);
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        padding: 16px 20px;
        border-bottom: 1px solid var(--color-border);
    }

    .data-table td {
        padding: 16px 20px;
        border-bottom: 1px solid var(--color-border-soft);
        vertical-align: middle;
    }

    .range-btn {
        background: transparent;
        border: none;
        font-weight: 800;
        letter-spacing: 0.05em;
        transition: all 0.2s;
    }

    .range-btn.btn--primary {
        background: var(--color-primary-dim);
        color: var(--color-primary);
        box-shadow: 0 0 15px var(--glow-primary);
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>