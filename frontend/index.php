<?php
require_once __DIR__ . '/config.php';
$pageTitle = 'Dashboard';
$activePage = 'dashboard';
$extraCss = ['/assets/css/main.css'];
$extraJs = ['/assets/js/dashboard.js'];
include __DIR__ . '/includes/header.php';
?>

<div class="page-header">
    <div>
        <h1 class="page-header__title">Trung tâm Điều phối</h1>
        <p class="page-header__subtitle">Quản lý camera & vi phạm giao thông — thời gian thực</p>
    </div>
    <button class="btn btn--outline btn--sm" onclick="location.reload()">
        <svg viewBox="0 0 20 20" fill="currentColor">
            <path fill-rule="evenodd"
                d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
                clip-rule="evenodd" />
        </svg>
        Làm mới
    </button>
</div>

<!-- Stats Grid -->
<div class="stats-grid" id="statsGrid">
    <div class="stat-card stat-card--red">
        <div class="stat-card__label">Vi phạm hôm nay</div>
        <div class="stat-card__value" id="statToday">—</div>
        <div class="stat-card__sub">lượt phát hiện</div>
    </div>
    <div class="stat-card stat-card--green">
        <div class="stat-card__label">Cameras online</div>
        <div class="stat-card__value" id="statOnline">—</div>
        <div class="stat-card__sub" id="statTotal">/ — cameras</div>
    </div>
    <div class="stat-card stat-card--blue">
        <div class="stat-card__label">Tổng vi phạm</div>
        <div class="stat-card__value" id="statAll">—</div>
        <div class="stat-card__sub">từ trước đến nay</div>
    </div>
</div>

<!-- Camera Cards -->
<div class="card" style="margin-bottom: 24px;">
    <div class="card__header">
        <span class="card__title">Cameras</span>
        <span id="cameraCountBadge" class="badge badge--gray">—</span>
    </div>
    <div class="card__body">
        <div class="camera-grid" id="cameraGrid">
            <div class="loading">Đang tải cameras...</div>
        </div>
    </div>
</div>

<!-- Recent Violations -->
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

<script>
    window.APP_CONFIG = { API_URL: '<?= API_URL ?>' };
</script>

<?php include __DIR__ . '/includes/footer.php'; ?>