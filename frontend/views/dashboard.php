<?php
use Frontend\App\Core\Page;

$page = new Page(
    title: 'Hệ thống Camera',
    activePage: 'dashboard',
    extraCss: ['/assets/css/pages/dashboard.css'],
    extraJs: ['/assets/js/dashboard.js'],
);

include __DIR__ . '/../includes/header.php';
?>

<div style="margin-bottom: 32px; display: flex; justify-content: space-between; align-items: center;">
    <div>
        <h1 style="font-size: 1.5rem; font-weight: 800; text-transform: uppercase; letter-spacing: -0.02em;">Thiết bị
            giám sát</h1>
        <p class="text-muted" style="font-size: 0.9rem;">Danh mục camera hoạt động trên toàn hệ thống.</p>
    </div>
    <div id="statusSummary" style="display: flex; gap: 16px;">
        <!-- Filled by JS -->
    </div>
</div>

<div class="camera-grid" id="cameraGrid">
    <div class="loading-state" style="grid-column: 1/-1; text-align: center; padding: 64px;">
        <div class="spinner" style="margin: 0 auto 16px;"></div>
        <p class="text-muted">Đang kết nối hệ thống...</p>
    </div>
</div>

<style>
    .camera-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 24px;
    }

    .cam-card {
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        cursor: pointer;
        border: 1px solid #1f1f1f;
    }

    .cam-card:hover {
        border-color: var(--color-primary);
        transform: translateY(-4px);
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.4);
    }

    .cam-card__preview {
        width: 100%;
        aspect-ratio: 16/9;
        background: #050505;
        position: relative;
        overflow: hidden;
    }

    .cam-card__preview img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0.8;
    }

    .cam-card__body {
        padding: 20px;
    }

    .cam-card__title {
        font-size: 1rem;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .cam-card__meta {
        font-size: 0.8rem;
        color: var(--color-text-dim);
    }

    .cam-card__status {
        position: absolute;
        top: 12px;
        right: 12px;
    }
</style>

<?= $page->configScript() ?>
<?php include __DIR__ . '/../includes/footer.php'; ?>