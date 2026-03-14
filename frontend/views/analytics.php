<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Phân tích dữ liệu AI',
    activePage: 'analytics',
    extraJs: [
        'https://cdn.jsdelivr.net/npm/chart.js',
        '/assets/js/analytics.js'
    ],
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px;">
    <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase;">Phân tích hệ thống</h1>
    <p class="text-muted">Trực quan hóa xu hướng vi phạm và hiệu suất Camera.</p>
</div>

<div style="display: grid; grid-template-columns: 2fr 1.2fr; gap: 24px; margin-bottom: 24px;">
    <!-- Trend Chart -->
    <div class="card">
        <div class="card__header"><span class="card__title">Xu hướng vi phạm (7 ngày)</span></div>
        <div class="card__body">
            <canvas id="trendChart" style="max-height: 350px;"></canvas>
        </div>
    </div>

    <!-- Distribution Chart -->
    <div class="card">
        <div class="card__header"><span class="card__title">Phân bổ theo Camera</span></div>
        <div class="card__body">
            <canvas id="distributionChart" style="max-height: 350px;"></canvas>
        </div>
    </div>
</div>

<div class="card">
    <div class="card__header"><span class="card__title">Khung giờ cao điểm (24H)</span></div>
    <div class="card__body">
        <canvas id="hourlyChart" style="max-height: 300px;"></canvas>
    </div>
</div>

<style>
    .card__body {
        position: relative;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>