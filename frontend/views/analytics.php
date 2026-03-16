<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'PHÂN TÍCH DỮ LIỆU',
    activePage: 'analytics',
    extraJs: ['/assets/js/pages/AnalyticsController.js']
);

include __DIR__ . '/../includes/header.php';
?>

<div class="view-header mb-2">
    <h1 class="uppercase bold" style="font-size: 1.5rem;">Phân tích dữ liệu</h1>
    <p class="text-dim uppercase" style="font-size: 0.7rem;">Dữ liệu tổng hợp trong 72 giờ qua</p>
</div>

<div class="analytics-grid">
    <div class="g-card" style="grid-column: 1/-1;">
        <div class="g-card__header">
            <span class="g-card__title">Tần suất vi phạm theo giờ</span>
        </div>
        <div class="g-card__body"
            style="height: 300px; display:flex; align-items:center; justify-content:center; background: var(--color-surface-soft); border-radius: 4px;">
            <div id="chart-container" class="font-mono text-dim">
                <div class="spinner"></div> ĐANG TẢI DỮ LIỆU...
            </div>
        </div>
    </div>
</div>

<style>
    .analytics-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 32px;
    }
</style>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>