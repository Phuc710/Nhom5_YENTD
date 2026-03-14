<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Quản lý Camera',
    activePage: 'cameras',
    extraCss: ['/assets/css/pages/dashboard.css'],
    extraJs: ['/assets/js/cameras.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px; display: flex; justify-content: space-between; align-items: flex-end;">
    <div>
        <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase;">Quản lý thiết bị</h1>
        <p class="text-muted">Danh sách camera và trạng thái phần cứng thời gian thực.</p>
    </div>
    <span id="cameraCountLabel" class="badge badge--online">CHẾ ĐỘ GIÁM SÁT</span>
</div>

<!-- Filters -->
<div class="card" style="margin-bottom: 24px; border-color: #1f1f1f; background: #050505;">
    <div class="card__body" style="padding: 24px;">
        <div style="display: grid; grid-template-columns: 1fr 1fr auto; gap: 24px;">
            <div class="filter-group">
                <label class="form-label">Tìm kiếm camera</label>
                <input type="text" id="cameraSearch" class="form-input" placeholder="Nhập tên hoặc vị trí..."
                    oninput="applyCameraFilter()">
            </div>

            <div class="filter-group">
                <label class="form-label">Trạng thái kết nối</label>
                <select id="cameraStatus" class="form-input" onchange="applyCameraFilter()">
                    <option value="">TẤT CẢ TRẠNG THÁI</option>
                    <option value="online">ĐANG ONLINE</option>
                    <option value="offline">ĐANG OFFLINE</option>
                </select>
            </div>

            <div class="filter-group" style="display: flex; align-items: flex-end;">
                <button class="btn btn--outline" onclick="resetCameraFilter()" style="height: 42px;">XÓA LỌC</button>
            </div>
        </div>
    </div>
</div>

<div class="camera-grid" id="cameraCatalog">
    <div class="loading-state" style="grid-column: 1/-1; text-align: center; padding: 64px;">
        <div class="spinner" style="margin: 0 auto 16px;"></div>
        <p class="text-muted">Đang tải danh mục thiết bị...</p>
    </div>
</div>

<style>
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
        background: #000;
        border: 1px solid #1f1f1f;
        padding: 10px 14px;
        color: #fff;
        border-radius: 4px;
        font-family: inherit;
    }

    .camera-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 24px;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>