<?php
require_once __DIR__ . '/bootstrap.php';

use Frontend\App\Core\Page;

$page = new Page(
    title: 'Trung tâm giám sát',
    activePage: 'dashboard',
    extraCss: ['/assets/css/camera.css'],
    extraJs: ['/assets/js/dashboard.js'],
    section: 'admin',
);

include __DIR__ . '/includes/header.php';
?>

<section class="hero-panel">
    <div class="hero-panel__grid">
        <div>
            <span class="hero-panel__eyebrow">Điều hành tập trung</span>
            <h1 class="hero-panel__title">Dashboard Trung tâm giám sát</h1>
            <p class="hero-panel__desc">
                Giao diện tác nghiệp tập trung để theo dõi camera, xem stream trực tiếp, kiểm tra hồ sơ vi phạm,
                quản lý zone và giám sát toàn hệ thống.
            </p>
            <div class="hero-actions">
                <a href="/cameras.php" class="btn btn--primary">Quản lý camera</a>
                <a href="/violations.php" class="btn btn--outline">Xem toàn bộ vi phạm</a>
            </div>
        </div>
        <div class="metric-stack">
            <div class="metric-stack__card">
                <div class="metric-stack__label">Vai trò web</div>
                <div class="metric-stack__value">Cảnh sát</div>
                <div class="metric-stack__desc">Web này phục vụ vận hành nội bộ và giám sát cho lực lượng quản trị.</div>
            </div>
            <div class="metric-stack__card">
                <div class="metric-stack__label">Mô hình triển khai</div>
                <div class="metric-stack__value">Hosting + Laptop</div>
                <div class="metric-stack__desc">Frontend trên hosting, backend và ThingsBoard trên máy nội bộ.</div>
            </div>
        </div>
    </div>
</section>

<div class="stats-grid" id="statsGrid">
    <div class="stat-card stat-card--red">
        <div class="stat-card__label">Vi phạm hôm nay</div>
        <div class="stat-card__value" id="statToday">—</div>
        <div class="stat-card__sub">Số lượt phát hiện trong ngày</div>
    </div>
    <div class="stat-card stat-card--green">
        <div class="stat-card__label">Camera online</div>
        <div class="stat-card__value" id="statOnline">—</div>
        <div class="stat-card__sub" id="statTotal">/ — camera toàn hệ thống</div>
    </div>
    <div class="stat-card stat-card--blue">
        <div class="stat-card__label">Tổng vi phạm</div>
        <div class="stat-card__value" id="statAll">—</div>
        <div class="stat-card__sub">Dữ liệu lưu từ trước đến nay</div>
    </div>
</div>

<div class="surface-grid" style="margin-bottom:24px;">
    <section class="surface-panel">
        <div class="surface-panel__title">Tác vụ chính</div>
        <div class="inline-actions">
            <a href="/cameras.php" class="btn btn--outline">Danh mục camera</a>
            <a href="/violations.php" class="btn btn--outline">Lịch sử vi phạm</a>
        </div>
        <p class="page-header__subtitle" style="margin-top:14px">
            Mỗi camera có trang cấu hình riêng để xem stream, stream URL, firmware, vị trí, zone và các vi phạm gần
            nhất.
        </p>
    </section>
    <section class="surface-panel">
        <div class="surface-panel__title">Phạm vi web</div>
        <ul style="display:grid;gap:10px;color:var(--color-text-muted);padding-left:18px;">
            <li>Web dành cho lực lượng cảnh sát và vận hành.</li>
            <li>Tập trung vào giám sát, camera, vi phạm và cấu hình hệ thống.</li>
            <li>Thông tin camera, trạng thái và vi phạm được đồng bộ từ backend theo thời gian thực gần đúng.</li>
        </ul>
    </section>
</div>

<div class="card" style="margin-bottom:24px;">
    <div class="card__header">
        <span class="card__title">Danh sách camera</span>
        <a href="/cameras.php" class="btn btn--outline btn--sm">Mở trang camera</a>
    </div>
    <div class="card__body">
        <div class="camera-grid" id="cameraGrid">
            <div class="loading">Đang tải camera...</div>
        </div>
    </div>
</div>

<div class="card">
    <div class="card__header">
        <span class="card__title">Vi phạm gần nhất</span>
        <a href="/violations.php" class="btn btn--outline btn--sm">Xem tất cả</a>
    </div>
    <div class="table-container">
        <table class="table">
            <thead>
                <tr>
                    <th>Ảnh</th>
                    <th>Biển số</th>
                    <th>Camera</th>
                    <th>Thời gian</th>
                    <th>Đèn</th>
                    <th>Confidence</th>
                    <th></th>
                </tr>
            </thead>
            <tbody id="recentTableBody">
                <tr>
                    <td colspan="7" class="loading">Đang tải...</td>
                </tr>
            </tbody>
        </table>
    </div>
</div>

<?= $page->configScript() ?>

<?php include __DIR__ . '/includes/footer.php'; ?>
