<?php
require_once __DIR__ . '/bootstrap.php';

use Frontend\App\Core\Page;

$page = new Page(
    title: 'Quản lý camera',
    activePage: 'cameras',
    extraCss: ['/assets/css/camera.css'],
    extraJs: ['/assets/js/cameras.js'],
    section: 'admin',
);

include __DIR__ . '/includes/header.php';
?>

<div class="page-header">
    <div>
        <h1 class="page-header__title">Danh mục camera</h1>
        <p class="page-header__subtitle">
            Xem toàn bộ camera, trạng thái online, stream URL, vị trí và truy cập nhanh sang trang cấu hình chi tiết.
        </p>
    </div>
    <a href="/index.php" class="btn btn--outline">Về trung tâm</a>
</div>

<div class="filter-bar">
    <div class="filter-group">
        <label>Tìm theo tên hoặc vị trí</label>
        <input type="text" id="cameraSearch" placeholder="Camera ngã tư, Quận 1..." oninput="applyCameraFilter()">
    </div>
    <div class="filter-group">
        <label>Trạng thái</label>
        <select id="cameraStatus" onchange="applyCameraFilter()">
            <option value="">Tất cả</option>
            <option value="online">Online</option>
            <option value="offline">Offline</option>
        </select>
    </div>
    <div class="filter-actions">
        <button class="btn btn--outline btn--sm" onclick="resetCameraFilter()">Xóa lọc</button>
    </div>
</div>

<div class="stats-grid" style="margin-bottom:24px;">
    <div class="stat-card stat-card--blue">
        <div class="stat-card__label">Tổng camera</div>
        <div class="stat-card__value" id="cameraTotal">—</div>
        <div class="stat-card__sub">Toàn bộ camera đã cấu hình</div>
    </div>
    <div class="stat-card stat-card--green">
        <div class="stat-card__label">Camera online</div>
        <div class="stat-card__value" id="cameraOnline">—</div>
        <div class="stat-card__sub">Thiết bị đang phản hồi</div>
    </div>
    <div class="stat-card stat-card--warn">
        <div class="stat-card__label">Camera offline</div>
        <div class="stat-card__value" id="cameraOffline">—</div>
        <div class="stat-card__sub">Thiết bị chưa phản hồi</div>
    </div>
</div>

<div class="card">
    <div class="card__header">
        <span class="card__title">Toàn bộ camera</span>
        <span id="cameraCountLabel" class="badge badge--gray">Đang tải...</span>
    </div>
    <div class="card__body">
        <div class="camera-grid" id="cameraCatalog">
            <div class="loading">Đang tải danh sách camera...</div>
        </div>
    </div>
</div>

<?= $page->configScript() ?>

<?php include __DIR__ . '/includes/footer.php'; ?>
