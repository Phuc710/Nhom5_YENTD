<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'DANH SÁCH THIẾT BỊ',
    activePage: 'cameras',
    extraJs: ['/assets/js/pages/DevicesController.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-2 flex-between">
    <div>
        <h1 class="uppercase bold" style="font-size: 1.5rem;">Danh sách camera</h1>
        <p class="text-dim uppercase" style="font-size: 0.7rem;">Quản lý và thiết lập hệ thống camera giám sát</p>
    </div>
    <div class="view-actions">
        <!-- Add actions if needed -->
    </div>
</div>

<div class="g-card mb-2" style="background: var(--color-surface-soft);">
    <div class="g-card__body">
        <div class="filter-flex">
            <div class="filter-item" style="flex:1">
                <input type="text" id="device-search" class="g-input" placeholder="Tìm kiếm camera..."
                    autocomplete="off">
            </div>
            <div class="filter-item" style="width: 240px;">
                <select id="device-status" class="g-input">
                    <option value="">Tất cả trạng thái</option>
                    <option value="online">Đang hoạt động</option>
                    <option value="offline">Mất kết nối</option>
                </select>
            </div>
        </div>
    </div>
</div>

<div class="device-grid" id="device-grid">
    <!-- Loaded via DevicesController -->
    <div class="loading-state" style="grid-column: 1/-1; text-align: center; padding: 120px;">
        <p class="text-dim uppercase bold">Đang tải danh sách camera...</p>
    </div>
</div>

<style>
    .filter-flex {
        display: flex;
        gap: 24px;
    }

    .device-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
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

    .cam-card {
        cursor: pointer;
        transition: transform 0.2s, border-color 0.2s;
    }

    .cam-card:hover {
        transform: translateY(-4px);
        border-color: var(--color-primary);
    }

    .cam-card__media {
        aspect-ratio: 16/9;
        background: #000;
        position: relative;
        overflow: hidden;
    }

    .cam-card__media img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0.6;
        transition: opacity 0.3s;
    }

    .cam-card:hover img {
        opacity: 0.9;
    }

    .cam-card__status-bar {
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        background: rgba(0, 0, 0, 0.7);
        padding: 6px 12px;
        display: flex;
        align-items: center;
        gap: 8px;
        border-top: 1px solid rgba(255, 255, 255, 0.05);
    }

    .no-preview {
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        font-weight: 800;
        color: #333;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>